"""The `cassette` command."""

from __future__ import annotations

import asyncio
import fnmatch
import json
import sys
from pathlib import Path
from typing import Any

import click

from .cassette import read_cassette, read_scenario
from .config import Config, load_dotenv
from .config import load_config as _load_config
from .differ import diff_cassettes, diff_lines, summary
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


def load_config(path: str) -> Config:
    """Load the config, plus any `.env` next to it or in the working directory."""
    cfg = _load_config(path)
    load_dotenv(cfg.root / ".env", Path.cwd() / ".env")
    return cfg


_COLORS = {"add": "green", "remove": "red", "info": "yellow", "dim": "bright_black", "bad": "red"}
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
@click.option("--json", "as_json", is_flag=True, help="Machine-readable output.")
def test(
    scenario: str | None, config_path: str, offline: bool, model: str | None, pattern: str | None, as_json: bool
) -> None:
    """Replay scenarios against their cassettes."""
    cfg = load_config(config_path)
    ignore = cfg.diff.ignoreArgs
    failed = 0
    report: list[dict[str, Any]] = []
    for name in _pick(cfg, scenario or pattern):
        base = read_scenario(cfg.cassettes_path, name)
        run = asyncio.run(run_scenario(cfg, name, mode="replay", offline=offline, model=model, quiet=as_json))
        d = diff_cassettes(
            base, run.cassette, ignore_args=ignore, tolerance=cfg.diff.tolerance, fail_on=cfg.diff.failOn
        )
        # Offline replays every recorded model turn, so the output must reproduce exactly.
        output_broke = offline and not d.output_same
        ok = run.exit_code == 0 and d.ok and not output_broke
        failed += not ok
        report.append(
            {
                "scenario": name,
                "ok": ok,
                "agentExitCode": run.exit_code,
                "outputSimilarity": d.output_similarity,
                "counts": d.counts,
                "divergences": run.divergences,
            }
        )
        if as_json:
            continue
        mark = click.style("✓", fg="green") if ok else click.style("×", fg="red")
        suffix = ", output identical" if offline and d.output_same else ""
        click.echo(f"{mark} {name}  {summary(d)}{suffix}")
        for style, text in diff_lines(d, ignore):
            click.echo("    " + click.style(text, fg=_COLORS.get(style)))
        for dv in run.divergences:
            click.echo(f"    {click.style('!', fg='red')} {dv['reason']}")
        if run.exit_code != 0:
            click.echo(f"    agent exited with code {run.exit_code}")
        if output_broke:
            click.echo(f"    {click.style('!', fg='red')} offline output differs from the recording")
    if as_json:
        click.echo(json.dumps({"passed": not failed, "scenarios": report}, indent=2))
    else:
        click.echo(click.style(f"{failed} failed", fg="red") if failed else click.style("all passed", fg="green"))
    sys.exit(1 if failed else 0)


@main.command()
@click.argument("a", type=click.Path(exists=True, dir_okay=False))
@click.argument("b", type=click.Path(exists=True, dir_okay=False))
@click.option("--ignore-args", default="", help="Comma-separated argument names to ignore.")
def diff(a: str, b: str, ignore_args: str) -> None:
    """Diff two cassette files in the terminal."""
    ignore = [x for x in ignore_args.split(",") if x]
    d = diff_cassettes(read_cassette(a), read_cassette(b), ignore_args=ignore)
    click.echo(f"{a} → {b}  {summary(d)}")
    lines = diff_lines(d, ignore)
    for style, text in lines:
        click.echo("    " + click.style(text, fg=_COLORS.get(style)))
    if not lines:
        click.echo("    no differences")


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
