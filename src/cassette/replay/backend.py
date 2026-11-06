from __future__ import annotations

import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

from ..backend_types import CallResult, ToolInfo
from ..cassette import Cassette
from ..trace import append_trace
from .match import Matcher, Tolerance


class ReplayBackend:
    """Answers tool calls from a cassette. Never touches the real server."""

    def __init__(
        self,
        cassette: Cassette,
        *,
        server: str,
        trace_path: str | Path | None = None,
        ignore_args: list[str] | None = None,
        tolerance: Tolerance = "normalized",
        on_divergence: Callable[[str, str, dict[str, Any]], None] | None = None,
    ) -> None:
        self._cassette = cassette
        self._server = server
        self._trace = trace_path
        self._on_divergence = on_divergence
        self.matcher = Matcher(cassette, ignore_args or [], tolerance)

    async def list_tools(self) -> list[ToolInfo]:
        schemas = self._cassette.toolSchemas.get(self._server, [])
        return [{"name": t.name, "inputSchema": t.inputSchema or {"type": "object"}} for t in schemas]

    async def call_tool(self, name: str, args: dict[str, Any]) -> CallResult:
        start = time.perf_counter()
        hit = self.matcher.find(self._server, name, args)
        if hit is None:
            if self._on_divergence:
                self._on_divergence(self._server, name, args)
            reason = f"cassette: no recorded result for {name}({args})"
            if self._trace:
                append_trace(
                    self._trace,
                    {"type": "divergence", "server": self._server, "name": name, "args": args, "reason": reason},
                )
            return {"content": [{"type": "text", "text": reason}], "isError": True}
        result: CallResult = hit.result
        if self._trace:
            event: dict[str, Any] = {
                "type": "tool",
                "server": self._server,
                "name": name,
                "args": args,
                "result": result,
                # Replay answers instantly; report the recorded latency so runs compare like for like.
                "ms": hit.ms if hit.ms is not None else round((time.perf_counter() - start) * 1000),
            }
            if hit.isError:
                event["isError"] = True
            append_trace(self._trace, event)
        return result
