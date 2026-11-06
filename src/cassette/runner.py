"""Runs one scenario: start the agent with its MCP servers redirected through Cassette's proxy, then fold the trace."""

from __future__ import annotations

import asyncio
import json
import os
import re
import shutil
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

from .cassette import Cassette, build_cassette, cassette_path, read_scenario, write_cassette
from .config import Config, expand_env
from .model import REPLAY_MODEL_ENV, TRACE_ENV
from .trace import read_trace


@dataclass
class ScenarioRun:
    scenario: str
    cassette: Cassette
    exit_code: int
    stderr: str
    # Live calls that had no recorded answer (replay only).
    divergences: list[dict[str, Any]] = field(default_factory=list)
    written: Path | None = None  # cassette file written (record only)


def upper_snake(k: str) -> str:
    return re.sub(r"[^A-Za-z0-9]+", "_", re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", k)).upper()


def server_env_names(server: str) -> tuple[str, str]:
    """Env vars an agent reads to find each MCP server: MCP_<SERVER>_COMMAND and MCP_<SERVER>_ARGS (JSON array)."""
    s = upper_snake(server)
    return f"MCP_{s}_COMMAND", f"MCP_{s}_ARGS"


async def run_scenario(
    cfg: Config,
    scenario_name: str,
    *,
    mode: Literal["record", "replay"],
    offline: bool = False,
    model: str | None = None,
    quiet: bool = False,
) -> ScenarioRun:
    scenario = cfg.scenario(scenario_name)
    baseline = read_scenario(cfg.cassettes_path, scenario_name) if mode == "replay" else None
    if offline and baseline is None:
        raise ValueError("--offline needs replay mode")
    workdir = Path(tempfile.mkdtemp(prefix="cassette-run-"))
    trace = workdir / "trace.jsonl"
    try:
        env = {**os.environ, **cfg.agent.env, TRACE_ENV: str(trace), "CASSETTE_INPUT": json.dumps(scenario.input)}
        if model:
            env["MODEL"] = model
        for k, v in scenario.input.items():
            if isinstance(v, str):
                env[upper_snake(k)] = v
        if offline:
            env[REPLAY_MODEL_ENV] = str(cassette_path(cfg.cassettes_path, scenario_name))

        for name, server in cfg.servers.items():
            command, args = server.split()
            argv = [sys.executable, "-m", "cassette", "proxy", "--server", name, "--mode", mode, "--trace", str(trace)]
            if baseline is not None:
                argv += ["--cassette", str(cassette_path(cfg.cassettes_path, scenario_name))]
            if cfg.diff.ignoreArgs:
                argv += ["--ignore-args", ",".join(cfg.diff.ignoreArgs)]
            argv += ["--tolerance", cfg.diff.tolerance]
            if mode == "record":
                # Real-server command and env go via a private temp file, not argv, so secrets stay off ps.
                spec = workdir / f"server-{name}.json"
                spec.write_text(
                    json.dumps(
                        {"command": command, "args": args, "env": {k: expand_env(v) for k, v in server.env.items()}}
                    ),
                    encoding="utf-8",
                )
                os.chmod(spec, 0o600)
                argv += ["--spec", str(spec)]
            cmd_var, args_var = server_env_names(name)
            env[cmd_var] = argv[0]
            env[args_var] = json.dumps(argv[1:])

        code, stdout, stderr = await _exec(cfg.agent.command, cfg.root, env, quiet)
        events = read_trace(trace)
        agent_model = env.get("MODEL")
        cassette = build_cassette(
            events,
            scenario=scenario_name,
            input=scenario.input,
            output=stdout.strip(),
            agent={"model": agent_model} if agent_model else {},
        )
        divergences = [
            {k: e[k] for k in ("server", "name", "args", "reason")} for e in events if e.get("type") == "divergence"
        ]
        run = ScenarioRun(scenario_name, cassette, code, stderr, divergences)
        if mode == "record" and code == 0:
            run.written = write_cassette(cfg.cassettes_path, cassette)
        return run
    finally:
        shutil.rmtree(workdir, ignore_errors=True)


async def _exec(command: str, cwd: Path, env: dict[str, str], quiet: bool) -> tuple[int, str, str]:
    proc = await asyncio.create_subprocess_shell(
        command, cwd=cwd, env=env, stdin=asyncio.subprocess.DEVNULL,
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
    )  # fmt: skip
    assert proc.stdout and proc.stderr
    err_chunks: list[bytes] = []

    async def pump_err() -> None:
        while chunk := await proc.stderr.read(4096):  # type: ignore[union-attr]
            err_chunks.append(chunk)
            if not quiet:
                sys.stderr.buffer.write(chunk)
                sys.stderr.buffer.flush()

    out, _ = await asyncio.gather(proc.stdout.read(), pump_err())
    code = await proc.wait()
    # Normalize CRLF so a cassette recorded on Windows still matches a replay on Linux CI.
    text = out.decode("utf-8", "replace").replace("\r\n", "\n")
    return code, text, b"".join(err_chunks).decode("utf-8", "replace")
