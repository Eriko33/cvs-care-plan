"""SSE streaming demo for the LangGraph agent loop (test_langgraph_nodes.py).

This is a prototype endpoint on top of the LangGraph experiment code, kept
separate from the real /(index) generation flow (which still uses the
free-text Anthropic SDK path in careplan/llm.py) — see the earlier
conversation about not merging these prematurely.

Route: GET /api/stream-demo
"""
import json

from django.http import StreamingHttpResponse

import test_langgraph_nodes as graph_module

DEMO_PROMPT = (
    "Patient 68kg, ordered IVIG (Privigen) 2 g/kg total over 5 days. Search for the "
    "relevant label section, verify the dose math, then write 2-3 sentences covering "
    "the dose and one monitoring point."
)


def stream_care_plan_demo(request):
    def event_stream():
        app = graph_module.build_graph()
        initial_state = {
            "messages": [{"role": "user", "content": DEMO_PROMPT}],
            "round_number": 0,
            "mrn": "005678",
            "final_care_plan": None,
            "stop_reason": None,
        }

        for stream_type, chunk in app.stream(
            initial_state, config={"recursion_limit": 20}, stream_mode=["messages", "custom"]
        ):
            if stream_type == "custom":
                event = chunk  # already {"type": "tool_start"/"tool_done", "tool": ..., ...}
            elif stream_type == "messages":
                msg_chunk, metadata = chunk
                # Only the "agent" node's chunks are real token-by-token LLM
                # output — the "tools" node's chunks are a whole tool result
                # dumped as one blob, not incremental. Skip those here.
                if metadata.get("langgraph_node") != "agent":
                    continue
                text = getattr(msg_chunk, "text", None)
                if not text:
                    continue
                event = {"type": "token", "text": text}
            else:
                continue

            yield f"data: {json.dumps(event)}\n\n"

        yield f"data: {json.dumps({'type': 'done'})}\n\n"

    response = StreamingHttpResponse(event_stream(), content_type="text/event-stream")
    response["Cache-Control"] = "no-cache"
    response["X-Accel-Buffering"] = "no"  # relevant if this ever sits behind nginx
    return response
