"""Hand-built LangGraph StateGraph (not create_agent's black box this time),
to show exactly how the State/reducer mechanics work.

Two versions in this file:
  - CarePlanAgentState: messages use the add_messages reducer (correct)
  - BrokenState: messages is a plain list, no reducer (demonstrates the
    overwrite failure mode the user asked about)

Run inside the container:
    docker compose exec -T web python test_langgraph_state.py
"""
import os
from typing import Annotated, Optional, TypedDict

import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django.setup()

from langchain_anthropic import ChatAnthropic  # noqa: E402
from langchain_core.messages import AnyMessage, ToolMessage  # noqa: E402
from langchain_core.tools import tool  # noqa: E402
from langgraph.graph import END, START, StateGraph  # noqa: E402
from langgraph.graph.message import add_messages  # noqa: E402

from careplan.harness import check_dose_math as _check_dose_math  # noqa: E402
from rag.search import search as _search  # noqa: E402


@tool
def search_reference_material(query: str) -> str:
    """Search the drug label knowledge base for dosing/contraindication/monitoring reference material."""
    chunks = _search(query, top_k=3)
    return "\n".join(c.text for c in chunks)


@tool
def check_dose_math(text: str, weight_kg: float, dose_per_kg: float) -> str:
    """Verify a stated total dose against weight_kg x dose_per_kg."""
    return str(_check_dose_math(text, weight_kg, dose_per_kg))


TOOLS = [search_reference_material, check_dose_math]
TOOLS_BY_NAME = {t.name: t for t in TOOLS}
model = ChatAnthropic(model="claude-sonnet-5").bind_tools(TOOLS)

PROMPT = (
    "Patient 68kg, ordered IVIG (Privigen) 2 g/kg over 5 days. Search for the relevant "
    "label section, verify the dose math, then write one sentence with the total dose."
)


# ---------------------------------------------------------------------------
# 1. Correct version: messages use the add_messages reducer -> APPEND
# ---------------------------------------------------------------------------

class CarePlanAgentState(TypedDict):
    messages: Annotated[list[AnyMessage], add_messages]  # append, not overwrite
    round_number: int
    mrn: str
    final_care_plan: Optional[str]


def agent_node(state: CarePlanAgentState) -> dict:
    response = model.invoke(state["messages"])
    return {"messages": [response], "round_number": state["round_number"] + 1}


def tools_node(state: CarePlanAgentState) -> dict:
    last_message = state["messages"][-1]
    results = []
    for call in last_message.tool_calls:
        output = TOOLS_BY_NAME[call["name"]].invoke(call["args"])
        results.append(ToolMessage(content=str(output), tool_call_id=call["id"], name=call["name"]))
    return {"messages": results}


def finalize_node(state: CarePlanAgentState) -> dict:
    return {"final_care_plan": state["messages"][-1].text}


def should_continue(state: CarePlanAgentState) -> str:
    return "tools" if state["messages"][-1].tool_calls else "finalize"


def build_correct_graph():
    graph = StateGraph(CarePlanAgentState)
    graph.add_node("agent", agent_node)
    graph.add_node("tools", tools_node)
    graph.add_node("finalize", finalize_node)
    graph.add_edge(START, "agent")
    graph.add_conditional_edges("agent", should_continue, {"tools": "tools", "finalize": "finalize"})
    graph.add_edge("tools", "agent")
    graph.add_edge("finalize", END)
    return graph.compile()


def run_correct():
    print("=" * 20, "CORRECT: messages with add_messages reducer", "=" * 20)
    app = build_correct_graph()
    result = app.invoke(
        {"messages": [{"role": "user", "content": PROMPT}], "round_number": 0, "mrn": "005678", "final_care_plan": None},
        config={"recursion_limit": 20},
    )
    print("round_number:", result["round_number"])
    print("mrn:", result["mrn"])
    print("message count in final state:", len(result["messages"]))
    for m in result["messages"]:
        kind = type(m).__name__
        has_tool_calls = getattr(m, "tool_calls", None)
        preview = (m.text if hasattr(m, "text") and not has_tool_calls else str(m.content))[:80]
        print(f"  [{kind}] {preview}")
    print("final_care_plan:", result["final_care_plan"])


# ---------------------------------------------------------------------------
# 2. Broken version: messages is a plain list -> each node's return OVERWRITES it
# ---------------------------------------------------------------------------

class BrokenState(TypedDict):
    messages: list  # no Annotated[..., add_messages] -> default reducer is overwrite
    round_number: int


def broken_agent_node(state: BrokenState) -> dict:
    response = model.invoke(state["messages"])
    return {"messages": [response], "round_number": state["round_number"] + 1}  # replaces the whole list


def broken_tools_node(state: BrokenState) -> dict:
    last_message = state["messages"][-1]
    results = []
    for call in last_message.tool_calls:
        output = TOOLS_BY_NAME[call["name"]].invoke(call["args"])
        results.append(ToolMessage(content=str(output), tool_call_id=call["id"], name=call["name"]))
    return {"messages": results}  # also replaces the whole list


def broken_should_continue(state: BrokenState) -> str:
    return "tools" if state["messages"][-1].tool_calls else END


def build_broken_graph():
    graph = StateGraph(BrokenState)
    graph.add_node("agent", broken_agent_node)
    graph.add_node("tools", broken_tools_node)
    graph.add_edge(START, "agent")
    graph.add_conditional_edges("agent", broken_should_continue, {"tools": "tools", END: END})
    graph.add_edge("tools", "agent")
    return graph.compile()


def run_broken():
    print()
    print("=" * 20, "BROKEN: messages as plain list, no reducer", "=" * 20)
    app = build_broken_graph()
    try:
        result = app.invoke(
            {"messages": [{"role": "user", "content": PROMPT}], "round_number": 0},
            config={"recursion_limit": 20},
        )
        print("round_number:", result["round_number"])
        print("message count in final state:", len(result["messages"]))
        for m in result["messages"]:
            print(f"  [{type(m).__name__}] {str(m.content)[:100]}")
    except Exception as e:
        print(f"{type(e).__name__}: {e}")


if __name__ == "__main__":
    run_correct()
    run_broken()
