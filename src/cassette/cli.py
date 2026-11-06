"""The `cassette` command."""

from __future__ import annotations

import asyncio
import fnmatch
import sys
from typing import Any

import click

from .cassette import read_scenario
from .config import Config, load_config
from .proxy import ProxyOptions, run_proxy
from .runner import run_scenario


def _pick(cfg: Config, pattern: str | None) -> list[str]:
    names = [s.name for s in cfg.scenarios]
    if not pattern:
        return names
    hit = [n for n in names if fnmatch.fnmatchcase(n, pattern)]
    if not hit:
        raise click.ClickException(f'no scenario matches "{pattern}" (have: {", ".join(names)})')
    return hit


@click.group()
def main() -> None:
    """pytest for agents: record, replay, diff and assert agent runs."""
    # Windows consoles and pipes default to cp1252 and crash on the ✓/× marks.
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")


config_opt = click.option("-c", "--config", "config_path", default="cassette.yaml", help="Config file.")


@main.command()
@click.argument("scenario", required=False)
@config_opt
@click.option("--model", help="Override the agent's model.")
def record(scenario: str | None, config_path: str, model: str | None) -> None:
    """Run live (model + tools) and write cassettes."""
    cfg = load_config(config_path)
    failed = 0
    for name in _pick(cfg, scenario):
        run = asyncio.run(run_scenario(cfg, name, mode="record", model=model))
        if run.exit_code != 0:
            failed += 1
            click.echo(click.style("×", fg="red") + f" {name}  agent exited with code {run.exit_code}")
        else:
            click.echo(
                click.style("●", fg="green") + f" {name}  recorded {len(run.cassette.steps)} steps → {run.written}"
            )
    sys.exit(1 if failed else 0)


@main.command()
@click.argument("scenario", required=False)
@config_opt
@click.option("--offline", is_flag=True, help="Also replay the recorded model (no API calls).")
@click.option("--model", help="Try a different model.")
@click.option("--filter", "pattern", help="Only scenarios matching the glob.")
def test(scenario: str | None, config_path: str, offline: bool, model: str | None, pattern: str | None) -> None:
    """Replay scenarios against their cassettes."""
    cfg = load_config(config_path)
    failed = 0
    for name in _pick(cfg, scenario or pattern):
        base = read_scenario(cfg.cassettes_path, name)
        run = asyncio.run(run_scenario(cfg, name, mode="replay", offline=offline, model=model))
        same_output = run.cassette.output == base.output
        ok = run.exit_code == 0 and not run.divergences and (not offline or same_output)
        failed += not ok
        calls = len(run.cassette.tool_steps())
        extra = (", output identical" if same_output else ", output differs") if offline else ""
        mark = click.style("✓", fg="green") if ok else click.style("×", fg="red")
        click.echo(f"{mark} {name}  {calls} tool calls replayed, {len(run.divergences)} divergences{extra}")
        for d in run.divergences:
            click.echo(f"    {click.style('!', fg='red')} {d['reason']}")
        if run.exit_code != 0:
            click.echo(f"    agent exited with code {run.exit_code}")
    click.echo(click.style(f"{failed} failed", fg="red") if failed else click.style("all passed", fg="green"))
    sys.exit(1 if failed else 0)


@main.command(hidden=True)
@click.option("--server", required=True)
@click.option("--mode", type=click.Choice(["record", "replay"]), required=True)
@click.option("--trace", required=True)
@click.option("--cassette", "cassette_file")
@click.option("--spec")
@click.option("--ignore-args", default="")
@click.option("--tolerance", type=click.Choice(["exact", "normalized"]), default="normalized")
@click.argument("command", nargs=-1)
def proxy(command: tuple[str, ...], **o: Any) -> None:
    """Internal: the agent spawns this as its MCP server."""
    asyncio.run(
        run_proxy(
            ProxyOptions(
                server=o["server"],
                mode=o["mode"],
                trace_path=o["trace"],
                cassette_path=o["cassette_file"],
                spec_path=o["spec"],
                command=list(command),
                ignore_args=[a for a in o["ignore_args"].split(",") if a],
                tolerance=o["tolerance"],
            )
        )
    )


if __name__ == "__main__":
    main()
