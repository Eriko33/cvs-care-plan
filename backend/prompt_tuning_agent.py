"""Autonomous prompt-tuning agent, built on claude-agent-sdk.

Task: run eval.py, find the 3 worst-F1 patients, look at their mis-scored
items, edit only the prompt's "口径" (tone/criteria) section, save as v6,
point config.yaml at v6, rerun eval, report the before/after numbers.

Restricted to PROJECT_DIR (belt-and-suspenders: cwd + a path check inside
the permission callback, not just cwd alone). Every Bash command needs an
interactive y/n confirmation before it runs; Read/Write/Edit are auto-allowed
but only when the target path resolves inside PROJECT_DIR.

Run:
    python prompt_tuning_agent.py
"""
import asyncio
from pathlib import Path

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

PROJECT_DIR = Path("/path/to/your/eval/project").resolve()  # <- set this

TASK = """
跑一遍 eval.py，找出 F1 最低的三个病人，看判错条目。
只改 prompts/careplan_generation/v5.txt 里"口径"相关的部分（比如判定标准、措辞要求），
不要动整体结构、字数要求之外的其他内容。
把改完的版本存成 prompts/careplan_generation/v6.txt（v5.txt 保持不动，方便对比）。
把 config.yaml 里指向 prompt 版本的字段改成 v6。
再跑一遍 eval.py。
最后报告这三个病人改动前后各自的 precision / recall / F1，一共六组数字的对比。
"""


def _path_inside_project(raw_path: str) -> bool:
    try:
        resolved = (PROJECT_DIR / raw_path).resolve() if not Path(raw_path).is_absolute() else Path(raw_path).resolve()
    except Exception:
        return False
    return resolved == PROJECT_DIR or PROJECT_DIR in resolved.parents


async def confirm_tool(tool_name: str, tool_input: dict, context) -> "PermissionResultAllow | PermissionResultDeny":
    if tool_name == "Bash":
        command = tool_input.get("command", "")
        answer = await asyncio.to_thread(input, f"\n[需要确认] 即将执行命令:\n  {command}\n允许吗？(y/n) ")
        if answer.strip().lower() == "y":
            return PermissionResultAllow()
        return PermissionResultDeny(message="用户拒绝执行这条命令", interrupt=False)

    if tool_name in ("Write", "Edit"):
        file_path = tool_input.get("file_path", "")
        if not _path_inside_project(file_path):
            return PermissionResultDeny(message=f"{file_path} 不在项目目录 {PROJECT_DIR} 内，拒绝写入")
        return PermissionResultAllow()

    # Read / Glob / Grep：只读，风险低，直接放行（cwd 已经把默认查找范围限定在项目目录）
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
        cwd=str(PROJECT_DIR),
        allowed_tools=["Read", "Write", "Edit", "Bash", "Glob", "Grep"],
        can_use_tool=confirm_tool,
        max_turns=30,
    )

    async for message in query(prompt=TASK, options=options):
        if isinstance(message, AssistantMessage):
            for block in message.content:
                _print_content_block(block)
        elif isinstance(message, UserMessage):
            # tool_result 块实际是在 UserMessage 里回传的，不是 AssistantMessage
            if isinstance(message.content, list):
                for block in message.content:
                    _print_content_block(block, prefix="  ")
        elif isinstance(message, ResultMessage):
            print(f"\n=== 结束 ({message.subtype}) ===")
            print(f"  轮数: {message.num_turns} | 总花费: ${message.total_cost_usd} | 有错误: {message.is_error}")
            print(f"  最终结果:\n{message.result}")


if __name__ == "__main__":
    asyncio.run(main())
