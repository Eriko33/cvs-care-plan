"""The two core nodes — call_model_node ("调模型") and run_tools_node ("跑函数")
— built on the CarePlanAgentState from the previous step, wired to the full
three-tool set from careplan/agentic_tools.py.

Run inside the container:
    docker compose exec -T web python test_langgraph_nodes.py
"""
import os
from typing import Annotated, Optional, TypedDict

import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django.setup()

from langchain_anthropic import ChatAnthropic  # noqa: E402
from langchain_core.messages import AIMessage, AnyMessage, ToolMessage  # noqa: E402
from langchain_core.tools import tool  # noqa: E402
from langgraph.graph import END, START, StateGraph  # noqa: E402
from langgraph.graph.message import add_messages  # noqa: E402

from careplan.harness import check_dose_math as _check_dose_math  # noqa: E402
from careplan.review_protocol_loader import read_review_protocol as _read_review_protocol  # noqa: E402
from rag.search import search as _search  # noqa: E402


@tool
def search_reference_material(query: str) -> str:
    """Search the drug label knowledge base for reference material — dosing,
    contraindications, monitoring/lab requirements, warnings. Call this before
    writing about a specific drug so the content is grounded in the actual label
    text instead of general knowledge. You may call it more than once with
    different queries if one search doesn't cover everything you need."""
    chunks = _search(query, top_k=5)
    return "\n\n".join(c.text for c in chunks)


@tool
def check_dose_math(text: str, weight_kg: float, dose_per_kg: float) -> str:
    """Verify that a stated total dose (in grams) matches weight_kg x dose_per_kg.
    Call this right after drafting a sentence that states a calculated total dose,
    to catch arithmetic errors before finalizing the care plan."""
    return str(_check_dose_math(text, weight_kg, dose_per_kg))


@tool
def read_review_protocol(name: str) -> str:
    """Load the full step-by-step instructions for one named review protocol. The
    system prompt lists which protocols are available and when each one applies —
    call this only for a protocol whose trigger condition actually matches this case."""
    return _read_review_protocol(name)  # raises ValueError for an unknown name — not caught here on purpose


TOOLS = [search_reference_material, check_dose_math, read_review_protocol]
TOOLS_BY_NAME = {t.name: t for t in TOOLS}
model_with_tools = ChatAnthropic(model="claude-sonnet-5").bind_tools(TOOLS)


class CarePlanAgentState(TypedDict):
    messages: Annotated[list[AnyMessage], add_messages]
    round_number: int
    mrn: str
    final_care_plan: Optional[str]


def call_model_node(state: CarePlanAgentState) -> dict:
    """"调模型": send the conversation history + the three tool definitions to
    the model. The reply gets appended to history (via the add_messages
    reducer on the state) and the round counter goes up by one."""
    response = model_with_tools.invoke(state["messages"])
    return {
        "messages": [response],
        "round_number": state["round_number"] + 1,
    }


def run_tools_node(state: CarePlanAgentState) -> dict:
    """"跑函数": look at every tool call the model just requested, run them
    all, and append every result to history together. A function raising an
    exception does NOT crash this node — the error message becomes that
    call's result instead, marked with status="error" so the model (and any
    code inspecting the state) can tell it apart from a real result."""
    last_message = state["messages"][-1]
    tool_messages = []

    for call in last_message.tool_calls:
        try:
            output = TOOLS_BY_NAME[call["name"]].invoke(call["args"])
            tool_messages.append(
                ToolMessage(content=str(output), tool_call_id=call["id"], name=call["name"], status="success")
            )
        except Exception as exc:
            error_text = f"{type(exc).__name__}: {exc}"
            tool_messages.append(
                ToolMessage(content=error_text, tool_call_id=call["id"], name=call["name"], status="error")
            )

    return {"messages": tool_messages}


def should_continue(state: CarePlanAgentState) -> str:
    return "tools" if state["messages"][-1].tool_calls else "finalize"


def finalize_node(state: CarePlanAgentState) -> dict:
    return {"final_care_plan": state["messages"][-1].text}


def build_graph():
    graph = StateGraph(CarePlanAgentState)
    graph.add_node("agent", call_model_node)
    graph.add_node("tools", run_tools_node)
    graph.add_node("finalize", finalize_node)
    graph.add_edge(START, "agent")
    graph.add_conditional_edges("agent", should_continue, {"tools": "tools", "finalize": "finalize"})
    graph.add_edge("tools", "agent")
    graph.add_edge("finalize", END)
    return graph.compile()


def test_full_run():
    print("=" * 20, "full graph run", "=" * 20)
    app = build_graph()
    result = app.invoke(
        {
            "messages": [{"role": "user", "content": (
                "Patient 68kg, ordered IVIG (Privigen) 2 g/kg over 5 days. Search for the "
                "relevant label section, verify the dose math, then write one sentence with "
                "the total dose."
            )}],
            "round_number": 0,
            "mrn": "005678",
            "final_care_plan": None,
        },
        config={"recursion_limit": 20},
    )
    print("round_number:", result["round_number"])
    print("mrn:", result["mrn"])
    print("message count:", len(result["messages"]))
    print("final_care_plan:", result["final_care_plan"])


def test_run_tools_node_error_handling():
    print()
    print("=" * 20, "run_tools_node error handling (one bad call, one good call)", "=" * 20)
    # Bypass the real model here — build the AIMessage by hand so the test is
    # deterministic instead of depending on the model happening to misbehave.
    fake_ai_message = AIMessage(
        content="",
        tool_calls=[
            {"name": "search_reference_material", "args": {"query": "Privigen dosing"}, "id": "call_1"},
            {"name": "read_review_protocol", "args": {"name": "does_not_exist"}, "id": "call_2"},
        ],
    )
    state: CarePlanAgentState = {
        "messages": [fake_ai_message],
        "round_number": 1,
        "mrn": "005678",
        "final_care_plan": None,
    }
    update = run_tools_node(state)
    for msg in update["messages"]:
        print(f"  [{msg.name}] status={msg.status} | content={str(msg.content)[:120]}")


if __name__ == "__main__":
    test_full_run()
    test_run_tools_node_error_handling()
