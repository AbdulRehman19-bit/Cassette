from __future__ import annotations

from typing import Any

from anyio.streams.memory import MemoryObjectReceiveStream, MemoryObjectSendStream
from mcp import types
from mcp.server.lowlevel import Server
from mcp.shared.message import SessionMessage

from .backend import ToolBackend


def build_proxy_server(backend: ToolBackend, name: str = "cassette-proxy") -> Server[Any, Any]:
    """Presents `backend` to the agent as an MCP server. The agent cannot tell it from the real thing."""
    server: Server[Any, Any] = Server(name)

    @server.list_tools()  # type: ignore[no-untyped-call,untyped-decorator]
    async def _list_tools() -> list[types.Tool]:
        return [types.Tool.model_validate(t) for t in await backend.list_tools()]

    @server.call_tool(validate_input=False)  # type: ignore[untyped-decorator]
    async def _call_tool(tool_name: str, arguments: dict[str, Any] | None) -> types.CallToolResult:
        return types.CallToolResult.model_validate(await backend.call_tool(tool_name, arguments or {}))

    return server


async def serve_proxy(
    backend: ToolBackend,
    read_stream: MemoryObjectReceiveStream[SessionMessage | Exception],
    write_stream: MemoryObjectSendStream[SessionMessage],
) -> None:
    server = build_proxy_server(backend)
    await server.run(read_stream, write_stream, server.create_initialization_options())
