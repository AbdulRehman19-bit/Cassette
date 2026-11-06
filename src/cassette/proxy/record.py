from __future__ import annotations

import time
from pathlib import Path
from typing import Any

from ..trace import append_trace
from .backend import CallResult, ToolBackend, ToolInfo


class RecordingBackend:
    """Wraps a backend so every tool listing and call is appended to the trace."""

    def __init__(self, backend: ToolBackend, *, server: str, trace_path: str | Path) -> None:
        self._backend = backend
        self._server = server
        self._trace = trace_path

    async def list_tools(self) -> list[ToolInfo]:
        tools = await self._backend.list_tools()
        append_trace(
            self._trace,
            {
                "type": "tools",
                "server": self._server,
                "tools": [{"name": t["name"], "inputSchema": t.get("inputSchema")} for t in tools],
            },
        )
        return tools

    async def call_tool(self, name: str, args: dict[str, Any]) -> CallResult:
        start = time.perf_counter()
        try:
            result = await self._backend.call_tool(name, args)
        except Exception as e:
            result = {"content": [{"type": "text", "text": str(e)}], "isError": True}
            self._log(name, args, result, start)
            raise
        self._log(name, args, result, start)
        return result

    def _log(self, name: str, args: dict[str, Any], result: CallResult, start: float) -> None:
        event: dict[str, Any] = {
            "type": "tool",
            "server": self._server,
            "name": name,
            "args": args,
            "result": result,
            "ms": round((time.perf_counter() - start) * 1000),
        }
        if result.get("isError"):
            event["isError"] = True
        append_trace(self._trace, event)
