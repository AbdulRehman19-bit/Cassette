"""What the proxy forwards to. Live = the real MCP server; replay = a cassette."""

from __future__ import annotations

import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from typing import Any, Protocol

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import get_default_environment, stdio_client

ToolInfo = dict[str, Any]  # {"name", "description"?, "inputSchema"}
CallResult = dict[str, Any]  # {"content": [...], "isError"?: True}


class ToolBackend(Protocol):
    async def list_tools(self) -> list[ToolInfo]: ...

    async def call_tool(self, name: str, args: dict[str, Any]) -> CallResult: ...


@dataclass
class StdioServerSpec:
    command: str
    args: list[str] = field(default_factory=list)
    env: dict[str, str] = field(default_factory=dict)


class LiveBackend:
    def __init__(self, session: ClientSession) -> None:
        self._session = session

    async def list_tools(self) -> list[ToolInfo]:
        tools: list[ToolInfo] = []
        cursor: str | None = None
        while True:
            page = await self._session.list_tools(cursor)
            tools += [t.model_dump(mode="json", exclude_none=True) for t in page.tools]
            cursor = page.nextCursor
            if not cursor:
                return tools

    async def call_tool(self, name: str, args: dict[str, Any]) -> CallResult:
        res = await self._session.call_tool(name, args)
        out: CallResult = res.model_dump(mode="json", exclude_none=True, by_alias=True)
        if not out.get("isError"):
            out.pop("isError", None)  # keep cassettes free of `isError: false`
        return out


@asynccontextmanager
async def open_live(spec: StdioServerSpec) -> AsyncIterator[LiveBackend]:
    """Spawn the real MCP server over stdio and talk to it as a client."""
    params = StdioServerParameters(
        command=spec.command, args=spec.args, env={**get_default_environment(), **os.environ, **spec.env}
    )
    async with stdio_client(params) as (read, write), ClientSession(read, write) as session:
        await session.initialize()
        yield LiveBackend(session)
