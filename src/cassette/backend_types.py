"""Types shared by the proxy (record) and replay backends; kept here so neither package imports the other."""

from __future__ import annotations

from typing import Any, Protocol

ToolInfo = dict[str, Any]  # {"name", "description"?, "inputSchema"}
CallResult = dict[str, Any]  # {"content": [...], "isError"?: True}


class ToolBackend(Protocol):
    async def list_tools(self) -> list[ToolInfo]: ...

    async def call_tool(self, name: str, args: dict[str, Any]) -> CallResult: ...
