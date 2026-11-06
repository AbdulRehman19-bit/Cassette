"""A read-only GitHub MCP server exposing only the tools ChangelogCat is allowed to use."""

from __future__ import annotations

import json
import os
from typing import Any

from mcp import types
from mcp.server.lowlevel import Server
from mcp.server.stdio import stdio_server

from .api import API, GitHub, GitHubError

_REPO = {"owner": {"type": "string"}, "repo": {"type": "string"}}

TOOLS = [
    types.Tool(
        name="list_pull_requests",
        description=(
            "List pull requests of a repository (number, title, state, merged_at, author, labels). "
            "Pass from_ref and to_ref (tags or branches) to get only the PRs merged between them, oldest first."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                **_REPO,
                "state": {"type": "string", "enum": ["open", "closed", "all"]},
                "from_ref": {"type": "string", "description": "Older tag/ref (exclusive)."},
                "to_ref": {"type": "string", "description": "Newer tag/ref (inclusive)."},
                "per_page": {"type": "number"},
                "page": {"type": "number"},
            },
            "required": ["owner", "repo"],
        },
    ),
    types.Tool(
        name="get_pull_request",
        description="Get one pull request: title, body, labels, author and change counts.",
        inputSchema={
            "type": "object",
            "properties": {**_REPO, "pull_number": {"type": "number"}},
            "required": ["owner", "repo", "pull_number"],
        },
    ),
    types.Tool(
        name="get_pull_request_diff",
        description="Get the unified diff of a pull request (truncated if very large).",
        inputSchema={
            "type": "object",
            "properties": {**_REPO, "pull_number": {"type": "number"}},
            "required": ["owner", "repo", "pull_number"],
        },
    ),
    types.Tool(
        name="get_file_contents",
        description="Read a file (or list a directory) in a repository at an optional ref.",
        inputSchema={
            "type": "object",
            "properties": {**_REPO, "path": {"type": "string"}, "ref": {"type": "string"}},
            "required": ["owner", "repo", "path"],
        },
    ),
]
TOOL_NAMES = {t.name for t in TOOLS}


async def dispatch(gh: GitHub, name: str, args: dict[str, Any]) -> str:
    if name not in TOOL_NAMES:
        raise GitHubError(f"unknown tool: {name}")
    result = await getattr(gh, name)(**args)
    return result if isinstance(result, str) else json.dumps(result, ensure_ascii=False)


def build_server(gh: GitHub) -> Server[Any, Any]:
    server: Server[Any, Any] = Server("readonly-github")

    @server.list_tools()  # type: ignore[no-untyped-call,untyped-decorator]
    async def _list() -> list[types.Tool]:
        return TOOLS

    @server.call_tool(validate_input=False)  # type: ignore[untyped-decorator]
    async def _call(name: str, arguments: dict[str, Any] | None) -> types.CallToolResult:
        try:
            text, is_error = await dispatch(gh, name, arguments or {}), False
        except (GitHubError, TypeError) as e:  # TypeError: wrong/missing arguments from the model
            text, is_error = f"Error: {e}", True
        return types.CallToolResult(content=[types.TextContent(type="text", text=text)], isError=is_error)

    return server


async def run() -> None:
    token = os.environ.get("GITHUB_PERSONAL_ACCESS_TOKEN") or os.environ.get("GITHUB_TOKEN", "")
    gh = GitHub(token, base_url=os.environ.get("GITHUB_API_URL", API))
    server = build_server(gh)
    try:
        async with stdio_server() as (read, write):
            await server.run(read, write, server.create_initialization_options())
    finally:
        await gh.aclose()
