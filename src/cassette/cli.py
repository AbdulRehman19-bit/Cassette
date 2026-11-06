"""The `cassette` command."""

from __future__ import annotations

import asyncio
import fnmatch
import json
import sys
from pathlib import Path
from typing import Any

import click

from .assertions import validate_assertions
from .cassette import ToolStep, cassette_path, read_cassette, read_scenario, write_cassette
from .config import Config, load_dotenv
from .config import load_config as _load_config
from .differ import diff_cassettes, diff_lines, summary
from .evaluate import ScenarioResult, evaluate_scenario
from .proxy import ProxyOptions, run_proxy
from .report import build_report, load_report, write_report
from .runner import probe_live_schemas, run_scenario


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
    # Nearest .env wins: config dir, then each parent up to the filesystem root, then the working directory.
    load_dotenv(*(d / ".env" for d in (cfg.root, *cfg.root.parents)), Path.cwd() / ".env")
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


report_dir_opt = click.option(
    "--report-dir",
    default="cassette-report",
    show_default=True,
    help="Where results.json, index.html and comment.md go.",
)


@main.command()
@click.argument("scenario", required=False)
@config_opt
@click.option("--offline", is_flag=True, help="Also replay the recorded model (no API calls).")
@click.option("--model", help="Try a different model.")
@click.option("--filter", "pattern", help="Only scenarios matching the glob.")
@click.option("--json", "as_json", is_flag=True, help="Machine-readable output.")
@click.option("--check-schemas", is_flag=True, help="List tools from the live servers to detect schema drift.")
@report_dir_opt
@click.option("--no-report", is_flag=True, help="Don't write the report files.")
def test(
    scenario: str | None,
    config_path: str,
    offline: bool,
    model: str | None,
    pattern: str | None,
    as_json: bool,
    check_schemas: bool,
    report_dir: str,
    no_report: bool,
) -> None:
    """Replay scenarios against their cassettes."""
    cfg = load_config(config_path)
    ignore = cfg.diff.ignoreArgs
    names = _pick(cfg, scenario or pattern)
    try:  # a typo in an assertion name must stop the run, not silently skip the check
        for sc in cfg.scenarios:
            validate_assertions([*cfg.assertions, *sc.assertions])
    except ValueError as e:
        raise click.ClickException(str(e)) from e
    live_schemas = asyncio.run(probe_live_schemas(cfg)) if check_schemas else None
    results: list[ScenarioResult] = []
    for name in names:
        base = read_scenario(cfg.cassettes_path, name)
        run = asyncio.run(run_scenario(cfg, name, mode="replay", offline=offline, model=model, quiet=as_json))
        res = evaluate_scenario(cfg, name, base, run, offline=offline, live_schemas=live_schemas)
        results.append(res)
        if not no_report:  # keep the run so `cassette update` can accept it as the new baseline
            write_cassette(Path(report_dir) / "runs", run.cassette)
        if not as_json:
            _print_result(res, ignore)

    report = build_report(results, offline=offline, model=model)
    if not no_report:
        paths = write_report(report, report_dir)
    if as_json:
        click.echo(json.dumps(report, indent=2, ensure_ascii=False))
    else:
        failed = report["summary"]["failed"]
        click.echo(click.style(f"{failed} failed", fg="red") if failed else click.style("all passed", fg="green"))
        if not no_report:
            click.echo(click.style(f"report: {paths['html']}", fg="bright_black"))
    sys.exit(0 if report["passed"] else 1)


def _print_result(res: ScenarioResult, ignore: list[str]) -> None:
    mark = click.style("✓", fg="green") if res.ok else click.style("×", fg="red")
    suffix = ", output identical" if res.offline and res.diff.output_same else ""
    click.echo(f"{mark} {res.name}  {summary(res.diff)}{suffix}")
    for style, text in diff_lines(res.diff, ignore):
        click.echo("    " + click.style(text, fg=_COLORS.get(style)))
    for dv in res.divergences:
        click.echo(f"    {click.style('!', fg='red')} {dv['reason']}")
    for c in res.checks:
        for f in c.failures:
            click.echo(f"    {click.style('×', fg='red')} {c.name}: {f.message}")
        if c.error:
            click.echo(f"    {click.style('×', fg='red')} {c.name}: check crashed: {c.error}")
        if c.skipped:
            click.echo("    " + click.style(f"- {c.name}: skipped ({c.skipped})", fg="bright_black"))
    if res.agent_exit_code != 0:
        click.echo(f"    agent exited with code {res.agent_exit_code}")
    if res.output_broke:
        click.echo(f"    {click.style('!', fg='red')} offline output differs from the recording")


@main.command()
@report_dir_opt
@click.option("--url", help="Link to put in the PR comment (e.g. the workflow artifact).")
def report(report_dir: str, url: str | None) -> None:
    """Rebuild the HTML report and PR comment from the last run."""
    try:
        data = load_report(report_dir)
    except FileNotFoundError:
        raise click.ClickException(f"no results in {report_dir}; run `cassette test` first") from None
    paths = write_report(data, report_dir, url)
    click.echo(f"rebuilt {paths['html']} and {paths['comment']}")


@main.command()
@click.argument("scenario", required=False)
@config_opt
@report_dir_opt
@click.option("--filter", "pattern", help="Only scenarios matching the glob.")
def update(scenario: str | None, config_path: str, report_dir: str, pattern: str | None) -> None:
    """Accept the last `cassette test` run as the new baseline (like `jest -u`)."""
    cfg = load_config(config_path)
    updated = 0
    for name in _pick(cfg, scenario or pattern):
        run_file = cassette_path(Path(report_dir) / "runs", name)
        if not run_file.exists():
            click.echo(f"- {name}  no saved run in {report_dir}/runs; run `cassette test` first")
            continue
        new = read_cassette(run_file)
        # A divergent call got an error from the cassette, not a real answer; accepting it would record a lie.
        if any(
            isinstance(s, ToolStep) and s.isError and "cassette: no recorded result" in str(s.result) for s in new.steps
        ):
            mark = click.style("×", fg="red")
            click.echo(
                f"{mark} {name}  the run called tools the cassette had no answer for; use `cassette record {name}`"
            )
            continue
        base_path = cassette_path(cfg.cassettes_path, name)
        if base_path.exists():
            old = read_cassette(base_path)
            d = diff_cassettes(old, new, ignore_args=cfg.diff.ignoreArgs, tolerance=cfg.diff.tolerance)
            click.echo(f"{click.style('●', fg='green')} {name}  baseline updated ({summary(d)})")
        else:
            click.echo(f"{click.style('●', fg='green')} {name}  baseline created")
        write_cassette(cfg.cassettes_path, new)
        updated += 1
    click.echo(f"{updated} baseline(s) updated")


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
