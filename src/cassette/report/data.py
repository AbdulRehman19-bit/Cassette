"""Turn evaluated scenarios into plain JSON-able report data. The HTML and Markdown renderers read only this,
so `cassette report` can rebuild both from the saved `results.json` without re-running anything."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

from .. import __version__
from ..cassette import Cassette, ToolStep
from ..differ import DiffEntry, args_delta
from ..evaluate import ScenarioResult

RESULT_CHARS = 2000
OUTPUT_CHARS = 6000


def _trim(text: str, limit: int) -> str:
    return text if len(text) <= limit else text[:limit] + f"\n… [{len(text) - limit} more chars]"


def _step(s: ToolStep | None) -> dict[str, Any] | None:
    if s is None:
        return None
    result = json.dumps(s.result, indent=2, ensure_ascii=False) if s.result is not None else ""
    return {
        "i": s.i,
        "name": s.name,
        "args": s.args,
        "result": _trim(result, RESULT_CHARS),
        "isError": bool(s.isError),
    }


def _row(e: DiffEntry) -> dict[str, Any]:
    row: dict[str, Any] = {"kind": e.kind, "base": _step(e.base), "new": _step(e.new)}
    if e.kind == "tool_args_changed" and e.base and e.new:
        row["delta"] = args_delta(e.base.args, e.new.args)
    return row


def _totals(c: Cassette, cost: float | None) -> dict[str, Any]:
    tin = sum((m.usage or {}).get("in", 0) for m in c.model_steps())
    tout = sum((m.usage or {}).get("out", 0) for m in c.model_steps())
    return {
        "model": c.agent.model,
        "tokensIn": tin,
        "tokensOut": tout,
        "latencyMs": round(sum(s.ms or 0 for s in c.steps)),
        "costUsd": cost,
        "modelCalls": len(c.model_steps()),
        "toolCalls": len(c.tool_steps()),
    }


def _first_divergence(r: ScenarioResult) -> list[DiffEntry]:
    """The first run of consecutive changed calls (e.g. a removed call plus the call that replaced it)."""
    entries = r.diff.entries
    start = next((i for i, e in enumerate(entries) if e.kind in r.diff.fail_on), None)
    if start is None:
        return []
    group = []
    for e in entries[start:]:
        if e.kind in ("same", "result_changed"):
            break
        group.append(e)
    return group


def scenario_data(r: ScenarioResult) -> dict[str, Any]:
    first_group = _first_divergence(r)
    return {
        "name": r.name,
        "ok": r.ok,
        "attack": r.attack,
        "agentExitCode": r.agent_exit_code,
        "divergences": [d["reason"] for d in r.divergences],
        "outputBroke": r.output_broke,
        "outputSimilarity": r.diff.output_similarity,
        "behaviorChangedButOutputFine": r.diff.behavior_changed_but_output_fine,
        "counts": r.diff.counts,
        "firstDivergence": [_row(e) for e in first_group],
        "rows": [_row(e) for e in r.diff.entries],
        "assertions": [
            {
                "name": c.name,
                "arg": c.arg,
                "ok": c.ok,
                "skipped": c.skipped,
                "failures": [f.message for f in c.failures] + ([f"check crashed: {c.error}"] if c.error else []),
            }
            for c in r.checks
        ],
        "output": {"base": _trim(r.base.output, OUTPUT_CHARS), "new": _trim(r.new.output, OUTPUT_CHARS)},
        "totals": {"base": _totals(r.base, r.base_cost_usd), "new": _totals(r.new, r.new_cost_usd)},
    }


def build_report(results: list[ScenarioResult], *, offline: bool = False, model: str | None = None) -> dict[str, Any]:
    scenarios = [scenario_data(r) for r in results]
    failed = [s for s in scenarios if not s["ok"]]
    base_tokens = sum(s["totals"]["base"]["tokensIn"] + s["totals"]["base"]["tokensOut"] for s in scenarios)
    new_tokens = sum(s["totals"]["new"]["tokensIn"] + s["totals"]["new"]["tokensOut"] for s in scenarios)
    return {
        "version": 1,
        "generatedAt": datetime.now(UTC).isoformat(timespec="seconds"),
        "cassetteVersion": __version__,
        "offline": offline,
        "modelOverride": model,
        "passed": not failed,
        "summary": {
            "scenarios": len(scenarios),
            "failed": len(failed),
            "changed": sum(1 for s in failed if not s["attack"] and (s["firstDivergence"] or s["outputBroke"])),
            "attacksCaught": sum(1 for s in failed if s["attack"]),
            "assertionFailures": sum(1 for s in scenarios for a in s["assertions"] if not a["ok"]),
            "tokensBase": base_tokens,
            "tokensNew": new_tokens,
            "tokensDeltaPct": round((new_tokens - base_tokens) / base_tokens * 100) if base_tokens else 0,
        },
        "scenarios": scenarios,
    }
