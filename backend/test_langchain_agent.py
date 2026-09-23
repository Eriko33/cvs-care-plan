"""Same agentic loop as careplan/agentic_tools.py, rebuilt with LangChain's
create_agent(), for direct comparison. Tool descriptions and system prompt
text are copied verbatim from the hand-written version.

Run inside the container:
    docker compose exec -T web python test_langchain_agent.py
"""
import json

from langchain.agents import create_agent
from langchain_core.messages import AIMessage, ToolMessage
from langchain_core.tools import tool

from careplan.harness import check_dose_math as _check_dose_math
from careplan.review_protocol_loader import build_protocol_index_text, read_review_protocol as _read_review_protocol
from rag.search import search as _search

MAX_ROUNDS = 8  # same cap as the hand-written loop


@tool
def search_reference_material(query: str) -> str:
    """Search the drug label knowledge base for reference material — dosing,
    contraindications, monitoring/lab requirements, warnings. Call this before
    writing about a specific drug so the content is grounded in the actual label
    text instead of general knowledge. You may call it more than once with
    different queries if one search doesn't cover everything you need."""
    chunks = _search(query, top_k=5)
    return json.dumps([{"section": c.section_name, "text": c.text} for c in chunks])


@tool
def check_dose_math(text: str, weight_kg: float, dose_per_kg: float) -> str:
    """Verify that a stated total dose (in grams) matches weight_kg x dose_per_kg.
    Call this right after drafting a sentence that states a calculated total dose,
    to catch arithmetic errors before finalizing the care plan."""
    return json.dumps(_check_dose_math(text, weight_kg, dose_per_kg))


@tool
def read_review_protocol(name: str) -> str:
    """Load the full step-by-step instructions for one named review protocol. The
    system prompt lists which protocols are available and when each one applies —
    call this only for a protocol whose trigger condition actually matches this case."""
    return json.dumps({"protocol": _read_review_protocol(name)})


TOOLS = [search_reference_material, check_dose_math, read_review_protocol]
SYSTEM_PROMPT = build_protocol_index_text()  # same index text the hand-written version uses

PROMPT = """You are a clinical pharmacist drafting a care plan section.

Patient: 68 kg, ordered IVIG (Privigen) 2 g/kg total over 5 days.
Home medications: Warfarin 5mg daily, Amiodarone 200mg daily, Metformin 500mg BID, Lisinopril 10mg daily.
Labs: INR 3.4 (supratherapeutic).

Write 2-4 sentences covering any safety concerns you identify for this patient, using the
available review protocols and reference search as appropriate."""


def main():
    agent = create_agent(model="claude-sonnet-5", tools=TOOLS, system_prompt=SYSTEM_PROMPT)

    round_number = 0
    final_text = None

    # stream_mode="values" yields the full message list after every graph step,
    # so consecutive yields let us see exactly what each round added.
    seen = 0
    for state in agent.stream(
        {"messages": [{"role": "user", "content": PROMPT}]},
        # LangGraph's recursion_limit counts graph STEPS, not rounds: each round
        # is normally 2 steps (agent node + tools node), except the final round
        # (agent node only, no tools node needed). Verified empirically with
        # recursion_limit=3 -> GraphRecursionError after exactly agent->tools->agent.
        config={"recursion_limit": MAX_ROUNDS * 2},
        stream_mode="values",
    ):
        messages = state["messages"]
        new_messages = messages[seen:]
        seen = len(messages)

        for msg in new_messages:
            if isinstance(msg, AIMessage) and msg.tool_calls:
                round_number += 1
                print(f"--- round {round_number}: model requested {len(msg.tool_calls)} tool call(s) ---")
                for call in msg.tool_calls:
                    print(f"  {call['name']}({call['args']})")
            elif isinstance(msg, ToolMessage):
                print(f"  -> {msg.name} result: {msg.content[:200]}")
            elif isinstance(msg, AIMessage) and not msg.tool_calls:
                # .content can be a list of blocks (thinking + text) rather than
                # a plain string once thinking is involved — .text() pulls just
                # the text portion, same fix as careplan/llm.py needed earlier.
                final_text = msg.text
                print(f"--- round {round_number + 1}: model finished, no more tool calls ---")

    print()
    print("=== final text ===")
    print(final_text)


if __name__ == "__main__":
    main()
