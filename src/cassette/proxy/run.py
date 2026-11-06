from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Literal

import anyio
from mcp.server.stdio import stdio_server

from ..cassette import read_cassette
from ..inject import InjectingBackend, load_fixture
from ..replay import ReplayBackend, Tolerance
from .backend import StdioServerSpec, ToolBackend, open_live
from .record import RecordingBackend
from .server import serve_proxy


@dataclass
class ProxyOptions:
    server: str
    mode: Literal["record", "replay"]
    trace_path: str
    cassette_path: str | None = None  # replay: cassette to answer from
    spec_path: str | None = None  # record: JSON {command,args,env}; keeps secrets off argv
    command: list[str] = field(default_factory=list)  # record: alternative to spec_path
    inject_path: str | None = None  # record: attack fixture to plant in live tool results
    ignore_args: list[str] = field(default_factory=list)
    tolerance: Tolerance = "normalized"


async def run_proxy(opts: ProxyOptions) -> None:
    """Process entrypoint for `cassette proxy`: the agent spawns this as its MCP server over stdio.

    In replay mode the real server is never spawned.
    """
    if opts.mode == "replay":
        if not opts.cassette_path:
            raise ValueError("replay mode needs a cassette path")
        backend: ToolBackend = ReplayBackend(
            read_cassette(opts.cassette_path),
            server=opts.server,
            trace_path=opts.trace_path,
            ignore_args=opts.ignore_args,
            tolerance=opts.tolerance,
        )
        async with stdio_server() as (read, write):
            await serve_proxy(backend, read, write)
        return

    if opts.spec_path:
        raw = json.loads(await anyio.Path(opts.spec_path).read_text(encoding="utf-8"))
        spec = StdioServerSpec(raw["command"], raw.get("args", []), raw.get("env", {}))
    elif opts.command:
        spec = StdioServerSpec(opts.command[0], opts.command[1:])
    else:
        raise ValueError("record mode needs the real server (--spec or a command)")
    async with open_live(spec) as live:
        source: ToolBackend = live
        if opts.inject_path:  # planted content is recorded like any real tool result
            source = InjectingBackend(live, load_fixture(opts.inject_path))
        backend = RecordingBackend(source, server=opts.server, trace_path=opts.trace_path)
        async with stdio_server() as (read, write):
            await serve_proxy(backend, read, write)
