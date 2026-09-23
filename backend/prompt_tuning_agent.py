"""Claude Agent SDK script, now wired to the Day-8 MCP server
(careplan/mcp_server.py) instead of raw filesystem/Bash tools.

Task: generate a care plan for MRN 002345 and save it — but print the draft
and wait for the pharmacist's confirmation BEFORE saving. On rejection, the
pharmacist's feedback goes back to the model so it can redraft.

IMPORTANT — verified vs. not verified (see conversation for details):
  - mcp_servers config shape, tool naming convention, PermissionResultDeny's
    `message` feeding back into the same turn: all confirmed against the
    installed claude-agent-sdk's real type signatures.
  - draft_care_plan/save_care_plan (the two new MCP tools this depends on):
    tested directly against real DB data — draft does NOT save, save does.
  - The full SDK <-> MCP server live run (query() actually talking to this
    MCP server, discovering its tools): NOT run end-to-end here — this
    container doesn't have the `claude` CLI binary the SDK shells out to.
    Everything below is correct per the verified API shapes, but hasn't
    been watched running as one live process.

Run (needs the `claude` CLI installed, not just the Python package):
    python prompt_tuning_agent.py
"""
import asyncio

from claude_agent_sdk import (
    AssistantMessage,
    ClaudeAgentOptions,
    PermissionResultAllow,
    PermissionResultDeny,
    ResultMessage,
    TextBlock,
    ToolResultBlock,
    ToolUseBlock,
    UserMessage,
    query,
)

# MCP server name — becomes the middle segment of every tool name:
# mcp__care-plan-system__draft_care_plan, mcp__care-plan-system__save_care_plan, etc.
MCP_SERVER_NAME = "care-plan-system"

MRN = "002345"

TASK = f"""
给 MRN {MRN} 生成一份 care plan。
先用 draft_care_plan 生成草稿，不要直接存库。
把草稿完整内容展示出来。
确认通过后，再用 save_care_plan 把这份内容存进系统。
如果草稿被拒绝并给了修改意见，根据意见重新生成一份草稿，再次展示等待确认，
直到确认通过为止。
"""


def mcp_tool_name(name: str) -> str:
    return f"mcp__{MCP_SERVER_NAME}__{name}"


async def confirm_tool(tool_name: str, tool_input: dict, context) -> "PermissionResultAllow | PermissionResultDeny":
    if tool_name == mcp_tool_name("save_care_plan"):
        print("\n" + "=" * 60)
        print("即将保存的 care plan 草稿：")
        print("=" * 60)
        print(tool_input.get("content", "(no content field found)"))
        print("=" * 60)

        answer = await asyncio.to_thread(input, "\n确认保存吗？(y/n) ")
        if answer.strip().lower() == "y":
            return PermissionResultAllow()

        feedback = await asyncio.to_thread(input, "拒绝了 —— 说说要改哪里: ")
        # message 会作为这次工具调用失败的原因回传给模型，同一轮对话里模型能看到、
        # 可以据此重新调用 draft_care_plan 生成新草稿 —— 不需要开新的 session。
        return PermissionResultDeny(
            message=f"药剂师拒绝保存，意见：{feedback}。请根据这个意见重新生成草稿，不要直接重试保存。",
            interrupt=False,
        )

    # draft_care_plan / read_care_plan / query_labs：只读或者只是生成草稿，不落库，直接放行
    return PermissionResultAllow()


def _print_content_block(block, prefix: str = ""):
    if isinstance(block, TextBlock):
        print(f"{prefix}[AI 说] {block.text}")
    elif isinstance(block, ToolUseBlock):
        print(f"{prefix}[调用工具] {block.name}({block.input})")
    elif isinstance(block, ToolResultBlock):
        status = "ERROR" if block.is_error else "ok"
        preview = str(block.content)[:200]
        print(f"{prefix}[工具结果:{status}] {preview}")


async def main():
    options = ClaudeAgentOptions(
        # stdio 方式接入 mcp_server.py —— 直接跑 python -m，因为这个脚本本来就假定
        # 在同一个装好 Django/Postgres 依赖的容器环境里运行。从容器外接的话，
        # 换成 command="docker", args=["compose", "exec", "-T", "web", "python", "-m", "careplan.mcp_server"]。
        mcp_servers={
            MCP_SERVER_NAME: {
                "type": "stdio",
                "command": "python",
                "args": ["-m", "careplan.mcp_server"],
            },
        },
        allowed_tools=[
            mcp_tool_name("draft_care_plan"),
            mcp_tool_name("save_care_plan"),
            mcp_tool_name("read_care_plan"),
            mcp_tool_name("query_labs"),
        ],
        can_use_tool=confirm_tool,
        max_turns=15,
    )

    async for message in query(prompt=TASK, options=options):
        if isinstance(message, AssistantMessage):
            for block in message.content:
                _print_content_block(block)
        elif isinstance(message, UserMessage):
            if isinstance(message.content, list):
                for block in message.content:
                    _print_content_block(block, prefix="  ")
        elif isinstance(message, ResultMessage):
            print(f"\n=== 结束 ({message.subtype}) ===")
            print(f"  轮数: {message.num_turns} | 总花费: ${message.total_cost_usd} | 有错误: {message.is_error}")
            print(f"  最终结果:\n{message.result}")


if __name__ == "__main__":
    asyncio.run(main())
