"""The PR comment: a summary line, a scenario table, and the first diverging step of each failure."""

from __future__ import annotations

import json
from typing import Any

MARKER = "<!-- cassette-report -->"  # lets the Action find and update its own comment instead of posting a new one


def fmt_call(step: dict[str, Any]) -> str:
    args = ", ".join(f"{k}: {json.dumps(v, ensure_ascii=False)}" for k, v in step["args"].items())
    return f"{step['name']}({args})"


def summary_line(report: dict[str, Any]) -> str:
    s = report["summary"]
    parts: list[str] = []
    if s["changed"]:
        parts.append(f"{s['changed']} changed")
    if s["attacksCaught"]:
        parts.append(f"{s['attacksCaught']} attack{'s' if s['attacksCaught'] != 1 else ''} caught")
    other = s["failed"] - s["changed"] - s["attacksCaught"]
    if other > 0:
        parts.append(f"{other} failed")
    if not parts:
        parts.append(f"all {s['scenarios']} scenarios passed")
    if s["tokensBase"]:
        parts.append(f"{s['tokensDeltaPct']:+d}% tokens")
    return ", ".join(parts)


def diff_block(rows: list[dict[str, Any]]) -> str:
    lines: list[str] = []
    for row in rows:
        if row["base"] and row["kind"] != "tool_added":
            lines.append(f"- step {row['base']['i']}  {fmt_call(row['base'])}")
        if row["new"] and row["kind"] != "tool_removed":
            lines.append(f"+ step {row['new']['i']}  {fmt_call(row['new'])}")
    return "```diff\n" + "\n".join(lines) + "\n```"


def render_comment(report: dict[str, Any], report_url: str | None = None) -> str:
    mark = "✅" if report["passed"] else "❌"
    out = [MARKER, f"### {mark} Cassette: {summary_line(report)}", ""]
    out += ["| Scenario | Result | Tool calls | Tokens | Notes |", "|---|---|---|---|---|"]
    for sc in report["scenarios"]:
        b, n = sc["totals"]["base"], sc["totals"]["new"]
        tokens = f"{b['tokensIn'] + b['tokensOut']} → {n['tokensIn'] + n['tokensOut']}"
        notes = []
        if sc["attack"]:
            notes.append("attack scenario")
        if sc["behaviorChangedButOutputFine"]:
            notes.append(f"output looks fine ({sc['outputSimilarity']:.2f}) but behavior changed")
        if sc["divergences"]:
            notes.append(f"{len(sc['divergences'])} unrecorded call(s)")
        result = "pass" if sc["ok"] else "**FAIL**"
        out.append(
            f"| `{sc['name']}` | {result} | {b['toolCalls']} → {n['toolCalls']} | {tokens} | {'; '.join(notes)} |"
        )

    for sc in (s for s in report["scenarios"] if not s["ok"]):
        out += ["", f"#### `{sc['name']}`"]
        if sc["firstDivergence"]:
            out += ["First diverging step:", diff_block(sc["firstDivergence"])]
        for a in sc["assertions"]:
            out += [f"- ❌ `{a['name']}`: {m}" for m in a["failures"]]
        if sc["outputBroke"]:
            out.append("- ❌ offline output differs from the recording")
        if sc["agentExitCode"]:
            out.append(f"- ❌ agent exited with code {sc['agentExitCode']}")
    if report_url:
        out += ["", f"[Open the full report]({report_url})"]
    return "\n".join(out) + "\n"
