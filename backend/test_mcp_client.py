"""One-off script: connect to careplan/mcp_server.py as a real MCP client
over stdio, list tools, call one. This is the same mechanism Claude Desktop
uses, just driven programmatically instead of from the chat UI.

Run inside the container:
    docker compose exec -T web python test_mcp_client.py
"""
import asyncio

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


async def main():
    params = StdioServerParameters(command="python", args=["-m", "careplan.mcp_server"])

    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()

            tools = await session.list_tools()
            print("=== tools/list ===")
            for tool in tools.tools:
                print(f"- {tool.name}: {tool.description[:80]}...")
            print()

            print("=== tools/call: read_care_plan(mrn=001234) ===")
            result = await session.call_tool("read_care_plan", {"mrn": "001234"})
            for block in result.content:
                print(block.text[:300] if hasattr(block, "text") else block)
            print()

            print("=== tools/call: query_labs(mrn=001234, test_name=IgG) ===")
            result = await session.call_tool("query_labs", {"mrn": "001234", "test_name": "IgG"})
            for block in result.content:
                print(block.text if hasattr(block, "text") else block)


if __name__ == "__main__":
    asyncio.run(main())
