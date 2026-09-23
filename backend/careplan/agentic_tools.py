"""Agentic tool-use loop: Claude decides when to search the drug-label
knowledge base and when to verify its own dose math while drafting content.

Wraps two existing, plain (non-LLM) functions as tools:
  - rag.search.search()            -> "search_reference_material"
  - careplan.harness.check_dose_math() -> "check_dose_math"
"""
import json

import anthropic
from django.conf import settings

from rag.search import search

from .harness import check_dose_math
from .review_protocol_loader import build_protocol_index_text, read_review_protocol

MAX_ROUNDS = 8

TOOLS = [
    {
        "name": "search_reference_material",
        "description": (
            "Search the drug label knowledge base for reference material — dosing, "
            "contraindications, monitoring/lab requirements, warnings. Call this before "
            "writing about a specific drug so the content is grounded in the actual label "
            "text instead of general knowledge. You may call it more than once with "
            "different queries if one search doesn't cover everything you need."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "A focused search query, e.g. 'IVIG renal monitoring'",
                },
            },
            "required": ["query"],
            "additionalProperties": False,
        },
        "strict": True,
    },
    {
        "name": "check_dose_math",
        "description": (
            "Verify that a stated total dose (in grams) matches weight_kg x dose_per_kg. "
            "Call this right after drafting a sentence that states a calculated total dose, "
            "to catch arithmetic errors before finalizing the care plan."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "text": {
                    "type": "string",
                    "description": "The drafted text containing the stated dose to verify",
                },
                "weight_kg": {"type": "number", "description": "Patient's weight in kg"},
                "dose_per_kg": {"type": "number", "description": "Ordered dose per kg, e.g. 2.0 for 2 g/kg"},
            },
            "required": ["text", "weight_kg", "dose_per_kg"],
            "additionalProperties": False,
        },
        "strict": True,
    },
    {
        "name": "read_review_protocol",
        "description": (
            "Load the full step-by-step instructions for one named review protocol. The "
            "system prompt lists which protocols are available and when each one applies — "
            "call this only for a protocol whose trigger condition actually matches this case."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "The protocol's name, exactly as listed in the system prompt"},
            },
            "required": ["name"],
            "additionalProperties": False,
        },
        "strict": True,
    },
]


def _execute_tool(name: str, tool_input: dict) -> str:
    """Runs the real function and returns a JSON string for the tool_result content.

    Raises on bad input / unknown tool — the caller is responsible for
    catching this and reporting it back to the model rather than crashing.
    """
    if name == "search_reference_material":
        chunks = search(tool_input["query"], top_k=5)
        result = [{"section": c.section_name, "text": c.text} for c in chunks]
    elif name == "check_dose_math":
        result = check_dose_math(tool_input["text"], tool_input["weight_kg"], tool_input["dose_per_kg"])
    elif name == "read_review_protocol":
        result = {"protocol": read_review_protocol(tool_input["name"])}
    else:
        raise ValueError(f"Unknown tool: {name}")
    return json.dumps(result)


def generate_with_tools(prompt: str, system_prompt: str = "", max_tokens: int = 4000) -> dict:
    """
    system_prompt: your own instructions, if any. The review-protocol index
    (name + one-line trigger per protocol) is always appended to it — that
    index is cheap, but each protocol's full body is only loaded on demand
    via the read_review_protocol tool call.

    Returns:
      {"final_text": str, "rounds": int, "stopped_reason": "done" | "max_rounds", "decision_log": list[str]}
    """
    client = anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)
    full_system_prompt = f"{system_prompt}\n\n{build_protocol_index_text()}".strip()
    messages = [{"role": "user", "content": prompt}]
    decision_log: list[str] = []
    last_response = None

    for round_number in range(1, MAX_ROUNDS + 1):
        response = client.messages.create(
            model=settings.ANTHROPIC_MODEL,
            max_tokens=max_tokens,
            system=full_system_prompt,
            tools=TOOLS,
            messages=messages,
        )
        last_response = response
        messages.append({"role": "assistant", "content": response.content})

        tool_use_blocks = [block for block in response.content if block.type == "tool_use"]
        decision_log.append(
            f"round {round_number}: stop_reason={response.stop_reason}, tool_calls={len(tool_use_blocks)}"
        )

        if not tool_use_blocks:
            final_text = "".join(block.text for block in response.content if block.type == "text")
            decision_log.append(f"=> stopping: model finished (stop_reason={response.stop_reason})")
            return {
                "final_text": final_text,
                "rounds": round_number,
                "stopped_reason": "done",
                "decision_log": decision_log,
            }

        # Execute every tool call from this round, then send ALL results back together.
        tool_results = []
        for block in tool_use_blocks:
            try:
                output = _execute_tool(block.name, block.input)
                decision_log.append(f"  {block.name}({block.input}) -> ok")
                tool_results.append({"type": "tool_result", "tool_use_id": block.id, "content": output})
            except Exception as exc:
                error_message = f"{type(exc).__name__}: {exc}"
                decision_log.append(f"  {block.name}({block.input}) -> ERROR: {error_message}")
                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": error_message,
                    "is_error": True,
                })

        messages.append({"role": "user", "content": tool_results})

    final_text = "".join(block.text for block in last_response.content if block.type == "text")
    decision_log.append(f"=> stopping: hit MAX_ROUNDS={MAX_ROUNDS} while the model still wanted to call tools")
    return {
        "final_text": final_text,
        "rounds": MAX_ROUNDS,
        "stopped_reason": "max_rounds",
        "decision_log": decision_log,
    }
