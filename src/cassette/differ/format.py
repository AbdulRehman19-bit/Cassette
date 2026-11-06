"""Terminal rendering of a trajectory diff."""

from __future__ import annotations

import json
from typing import Any

from ..cassette import ToolStep
from .diff import DiffEntry, TrajectoryDiff

Line = tuple[str, str]  # (style, text); style is one of: add, remove, info, dim, bad


def fmt_call(s: ToolStep, ignore_args: list[str] | None = None) -> str:
    shown = {k: v for k, v in s.args.items() if k not in (ignore_args or [])}
    args = ", ".join(f"{k}: {json.dumps(v, ensure_ascii=False)}" for k, v in shown.items())
    return f"{s.name}({args})"


def args_delta(old: dict[str, Any], new: dict[str, Any]) -> str:
    parts = []
    for k in sorted(set(old) | set(new)):
        if old.get(k) != new.get(k):
            was = json.dumps(old[k], ensure_ascii=False) if k in old else "∅"
            now = json.dumps(new[k], ensure_ascii=False) if k in new else "∅"
            parts.append(f"{k}: {was} → {now}")
    return "; ".join(parts)


def entry_lines(e: DiffEntry, ignore_args: list[str] | None = None) -> list[Line]:
    if e.kind == "tool_removed" and e.base:
        return [("remove", f"- step {e.base.i}  {fmt_call(e.base, ignore_args)}")]
    if e.kind == "tool_added" and e.new:
        return [("add", f"+ step {e.new.i}  {fmt_call(e.new, ignore_args)}")]
    if e.kind == "tool_args_changed" and e.base and e.new:
        return [
            ("remove", f"- step {e.base.i}  {fmt_call(e.base, ignore_args)}"),
            ("add", f"+ step {e.new.i}  {fmt_call(e.new, ignore_args)}"),
            ("dim", f"  args changed: {args_delta(e.base.args, e.new.args)}"),
        ]
    if e.kind == "result_changed" and e.new:
        return [("info", f"~ step {e.new.i}  {e.new.name}: same call, different result")]
    return []


def diff_lines(d: TrajectoryDiff, ignore_args: list[str] | None = None) -> list[Line]:
    """The body under a scenario's header line: changed steps, output similarity, token/latency deltas."""
    lines: list[Line] = []
    for e in d.entries:
        lines += entry_lines(e, ignore_args)
    if d.changed or not d.output_same:
        note = " (looks fine; behavior changed)" if d.behavior_changed_but_output_fine else ""
        lines.append(("info", f"output similarity {d.output_similarity:.2f}{note}"))
    b, n = d.base_totals, d.new_totals
    if (b.tokens_in, b.tokens_out) != (n.tokens_in, n.tokens_out):
        lines.append(("dim", f"tokens {b.tokens_in}→{b.tokens_out} vs {n.tokens_in}→{n.tokens_out}"))
    return lines


def summary(d: TrajectoryDiff) -> str:
    """One-line status for a scenario header."""
    if d.ok and not d.changed:
        t = d.new_totals
        return f"{t.tool_calls} tool calls, {t.model_calls} model calls"
    if d.ok:
        return "trajectory differs, within tolerance"
    return "trajectory changed"
