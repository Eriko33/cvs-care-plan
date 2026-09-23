"""pytest suite for the LangGraph agent loop (test_langgraph_nodes.py) —
NO real API calls. The model and the three tools are replaced with fakes:

  - search_reference_material  <- "检索指南"（说明书/指南内容检索）
  - read_review_protocol       <- "查化验"（加载对应流程文件，这里用作查化验场景的占位）
  - check_dose_math            <- "比对"（剂量核对）

Run:
    docker compose exec -T web pytest test_agent_graph_offline.py -v -s
"""
from langchain_core.messages import AIMessage, ToolMessage

import test_langgraph_nodes as graph_module


class ScriptedFakeModel:
    """Replaces model_with_tools.invoke() — hands back responses in a fixed
    order, one per call, and records what messages it was given each time
    (needed to check "AI 第二轮有没有收到" the error result)."""

    def __init__(self, responses: list[AIMessage]):
        self.responses = list(responses)
        self.calls: list[list] = []

    def invoke(self, messages):
        self.calls.append(list(messages))
        return self.responses[len(self.calls) - 1]


class FakeTool:
    """Minimal stand-in for a LangChain @tool object — TOOLS_BY_NAME only
    needs .name and .invoke() to exist."""

    def __init__(self, name, fn):
        self.name = name
        self._fn = fn

    def invoke(self, args):
        return self._fn(**args)


def ai_calls(calls: list[dict]) -> AIMessage:
    """An AI turn that requests one or more tool calls."""
    return AIMessage(content="", tool_calls=calls)


def ai_final(text: str) -> AIMessage:
    """An AI turn that gives a final answer — no tool calls."""
    return AIMessage(content=text, tool_calls=[])


def install_fake_tools(monkeypatch, *, search_fn=None, protocol_fn=None, dose_fn=None):
    """Swaps TOOLS_BY_NAME for fakes returning canned data (or raising, for scenario c)."""
    tools_by_name = {
        "search_reference_material": FakeTool(
            "search_reference_material", search_fn or (lambda query: "FAKE GUIDELINE TEXT")
        ),
        "read_review_protocol": FakeTool(
            "read_review_protocol", protocol_fn or (lambda name: "FAKE LAB/PROTOCOL TEXT")
        ),
        "check_dose_math": FakeTool(
            "check_dose_math", dose_fn or (lambda text, weight_kg, dose_per_kg: {"match_found": True})
        ),
    }
    monkeypatch.setattr(graph_module, "TOOLS_BY_NAME", tools_by_name)


def fresh_state():
    return {
        "messages": [{"role": "user", "content": "test prompt"}],
        "round_number": 0,
        "mrn": "005678",
        "final_care_plan": None,
        "stop_reason": None,
    }


def run_and_print(app, initial_state, recursion_limit=20):
    """Walks the graph step by step. Prints, for every step: which node just
    ran (round_number after it), and what got added to the message history.
    Returns the final merged state (same shape app.invoke() would return)."""
    prev = initial_state
    final = initial_state
    for state in app.stream(initial_state, config={"recursion_limit": recursion_limit}, stream_mode="values"):
        added = state["messages"][len(prev["messages"]):]
        if added:
            print(f"  round_number={state['round_number']}  (+{len(added)} message(s))")
            for m in added:
                if isinstance(m, ToolMessage):
                    print(f"    + ToolMessage[{m.name}] status={m.status}: {str(m.content)[:90]}")
                elif isinstance(m, AIMessage) and m.tool_calls:
                    print(f"    + AIMessage: requests {[c['name'] for c in m.tool_calls]}")
                elif isinstance(m, AIMessage):
                    print(f"    + AIMessage (final): {m.text[:90]}")
        prev = state
        final = state
    return final


# ---------------------------------------------------------------------------
# (a) AI 第一轮就给最终回答，不要任何函数
# ---------------------------------------------------------------------------

def test_scenario_a_immediate_final_answer(monkeypatch):
    install_fake_tools(monkeypatch)
    fake_model = ScriptedFakeModel([ai_final("Here is the final care plan text.")])
    monkeypatch.setattr(graph_module, "model_with_tools", fake_model)

    print("\n=== scenario a: immediate final answer ===")
    app = graph_module.build_graph()
    final = run_and_print(app, fresh_state())

    assert final["round_number"] == 1
    assert final["stop_reason"] == "done"
    assert final["final_care_plan"] == "Here is the final care plan text."
    assert len(fake_model.calls) == 1  # model was only called once


# ---------------------------------------------------------------------------
# (b) 第一轮同时要 查化验(read_review_protocol) + 检索指南(search)，
#     第二轮要 比对(check_dose_math)，第三轮给最终回答
# ---------------------------------------------------------------------------

def test_scenario_b_multi_round_multi_tool(monkeypatch):
    install_fake_tools(monkeypatch)
    fake_model = ScriptedFakeModel([
        ai_calls([
            {"name": "read_review_protocol", "args": {"name": "renal_impairment_review"}, "id": "call_1"},
            {"name": "search_reference_material", "args": {"query": "dosing"}, "id": "call_2"},
        ]),
        ai_calls([
            {"name": "check_dose_math", "args": {"text": "136 g", "weight_kg": 68, "dose_per_kg": 2}, "id": "call_3"},
        ]),
        ai_final("Final answer after checking everything."),
    ])
    monkeypatch.setattr(graph_module, "model_with_tools", fake_model)

    print("\n=== scenario b: multi-round, multi-tool ===")
    app = graph_module.build_graph()
    final = run_and_print(app, fresh_state())

    assert final["round_number"] == 3
    assert final["stop_reason"] == "done"
    assert final["final_care_plan"] == "Final answer after checking everything."
    assert len(fake_model.calls) == 3
    # round 1 requested 2 tools in parallel -> 2 ToolMessages must appear before round 2's model call
    round_2_input = fake_model.calls[1]
    tool_results_seen = [m for m in round_2_input if isinstance(m, ToolMessage)]
    assert len(tool_results_seen) == 2


# ---------------------------------------------------------------------------
# (c) 查化验的假函数抛异常：错误信息要作为结果传回去，AI 第二轮要收到
# ---------------------------------------------------------------------------

def test_scenario_c_tool_exception_is_reported_not_crashed(monkeypatch):
    def failing_protocol_lookup(name):
        raise RuntimeError("boom: lab/protocol system unavailable")

    install_fake_tools(monkeypatch, protocol_fn=failing_protocol_lookup)
    fake_model = ScriptedFakeModel([
        ai_calls([{"name": "read_review_protocol", "args": {"name": "renal_impairment_review"}, "id": "call_1"}]),
        ai_final("Noted the error and proceeded without that protocol."),
    ])
    monkeypatch.setattr(graph_module, "model_with_tools", fake_model)

    print("\n=== scenario c: tool raises, must not crash the graph ===")
    app = graph_module.build_graph()
    final = run_and_print(app, fresh_state())  # must not raise

    assert final["stop_reason"] == "done"
    assert final["round_number"] == 2

    # Did round 2's call to "the AI" actually include the error as a tool result?
    round_2_input = fake_model.calls[1]
    error_messages = [m for m in round_2_input if isinstance(m, ToolMessage) and m.status == "error"]
    assert len(error_messages) == 1
    assert "boom: lab/protocol system unavailable" in error_messages[0].content
    assert "RuntimeError" in error_messages[0].content


# ---------------------------------------------------------------------------
# (d) AI 每一轮都要同一个函数：第 8 轮该停下来并记录，第 9 轮绝不能发生
# ---------------------------------------------------------------------------

def test_scenario_d_stops_at_max_rounds(monkeypatch):
    install_fake_tools(monkeypatch)
    # 10 scripted responses so we can prove the 9th and 10th are NEVER consumed.
    responses = [
        ai_calls([{"name": "search_reference_material", "args": {"query": f"q{i}"}, "id": f"call_{i}"}])
        for i in range(10)
    ]
    fake_model = ScriptedFakeModel(responses)
    monkeypatch.setattr(graph_module, "model_with_tools", fake_model)

    print("\n=== scenario d: model always wants another tool call ===")
    app = graph_module.build_graph()
    final = run_and_print(app, fresh_state())

    assert final["round_number"] == graph_module.MAX_ROUNDS
    assert final["stop_reason"] == f"hit MAX_ROUNDS={graph_module.MAX_ROUNDS} while the model still wanted to call tools"
    assert len(fake_model.calls) == graph_module.MAX_ROUNDS  # the model was never called a 9th time


# ---------------------------------------------------------------------------
# (5) 画图：两个会一直循环的 node（agent/tools）+ 一条从 agent 出发的条件边
# ---------------------------------------------------------------------------

def test_graph_diagram_renders(tmp_path):
    app = graph_module.build_graph()
    out_path = tmp_path / "graph_offline_test.png"
    png_bytes = app.get_graph().draw_mermaid_png()
    out_path.write_bytes(png_bytes)

    assert out_path.exists()
    assert out_path.stat().st_size > 0

    # Also save a copy next to this file so it's easy to find without digging into tmp_path.
    saved_path = "graph_from_pytest.png"
    with open(saved_path, "wb") as f:
        f.write(png_bytes)
    print(f"\nsaved diagram to {saved_path} ({len(png_bytes)} bytes)")
