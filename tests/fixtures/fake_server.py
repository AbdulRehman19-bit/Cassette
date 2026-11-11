"""A tiny deterministic MCP server. Every tool call appends a line to LIVE_COUNT_FILE,
so tests can prove whether the "real" server was touched."""

import asyncio
import json
import os
from datetime import UTC, datetime

from mcp import types
from mcp.server.lowlevel import Server
from mcp.server.stdio import stdio_server

server = Server("fake-github")

TOOLS = [
    types.Tool(
        name="list_pull_requests",
        description="list",
        inputSchema={"type": "object", "properties": {"state": {"type": "string"}}},
    ),
    types.Tool(
        name="get_pull_request",
        description="get",
        inputSchema={"type": "object", "properties": {"number": {"type": "number"}}},
    ),
    types.Tool(
        name="create_issue",
        description="create",
        inputSchema={"type": "object", "properties": {"title": {"type": "string"}}},
    ),
]


@server.list_tools()
async def list_tools() -> list[types.Tool]:
    return TOOLS


@server.call_tool(validate_input=False)
async def call_tool(name: str, arguments: dict | None) -> types.CallToolResult:
    if path := os.environ.get("LIVE_COUNT_FILE"):
        with open(path, "a", encoding="utf-8") as f:  # noqa: ASYNC230
            f.write(name + "\n")
    if name == "create_issue":
        return types.CallToolResult(content=[types.TextContent(type="text", text="issue created")])
    if name == "list_pull_requests":
        text = json.dumps([{"number": 7, "title": "Add dark mode", "merged_at": datetime.now(UTC).isoformat()}])
    else:
        text = json.dumps(
            {"number": (arguments or {}).get("number"), "title": "Add dark mode", "body": "Adds a dark theme."}
        )
    return types.CallToolResult(content=[types.TextContent(type="text", text=text)])


async def main() -> None:
    async with stdio_server() as (read, write):
        await server.run(read, write, server.create_initialization_options())


asyncio.run(main())
