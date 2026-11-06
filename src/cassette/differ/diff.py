"""Trajectory diff: align the baseline and new tool-call sequences and report what changed."""

from __future__ import annotations

import difflib
import re
from dataclasses import dataclass, field
from typing import Literal

from ..cassette import Cassette, ToolStep, dumps, normalize
from ..replay.match import Tolerance, args_key

Kind = Literal["same", "tool_added", "tool_removed", "tool_args_changed", "result_changed"]
DEFAULT_FAIL_ON: tuple[str, ...] = ("tool_added", "tool_removed", "tool_args_changed")
# Output this similar reads as "fine" to a human skimming it; used to flag silent behavior changes.
LOOKS_FINE = 0.8


@dataclass(frozen=True)
class DiffEntry:
    kind: Kind
    base: ToolStep | None = None
    new: ToolStep | None = None

    @property
    def step(self) -> ToolStep:
        s = self.new or self.base
        assert s is not None
        return s


@dataclass
class Totals:
    tokens_in: int = 0
    tokens_out: int = 0
    latency_ms: float = 0.0
    model_calls: int = 0
    tool_calls: int = 0


@dataclass
class TrajectoryDiff:
    entries: list[DiffEntry]
    output_similarity: float
    base_totals: Totals
    new_totals: Totals
    fail_on: tuple[str, ...] = DEFAULT_FAIL_ON
    counts: dict[str, int] = field(default_factory=dict)

    @property
    def output_same(self) -> bool:
        return self.output_similarity >= 1.0

    @property
    def failures(self) -> list[DiffEntry]:
        return [e for e in self.entries if e.kind in self.fail_on]

    @property
    def changed(self) -> bool:
        return any(e.kind != "same" for e in self.entries)

    @property
    def ok(self) -> bool:
        return not self.failures

    @property
    def behavior_changed_but_output_fine(self) -> bool:
        """The headline case: the trajectory changed yet the final text still reads fine."""
        return bool(self.failures) and self.output_similarity >= LOOKS_FINE


def output_similarity(a: str, b: str) -> float:
    """0..1 similarity of two output texts, insensitive to whitespace."""
    na, nb = re.sub(r"\s+", " ", a.strip()), re.sub(r"\s+", " ", b.strip())
    if na == nb:
        return 1.0
    return round(difflib.SequenceMatcher(None, na, nb, autojunk=False).ratio(), 4)


def _totals(c: Cassette) -> Totals:
    t = Totals(tool_calls=len(c.tool_steps()), model_calls=len(c.model_steps()))
    for s in c.steps:
        t.latency_ms += s.ms or 0
    for m in c.model_steps():
        t.tokens_in += (m.usage or {}).get("in", 0)
        t.tokens_out += (m.usage or {}).get("out", 0)
    return t


def _lcs_pairs(a: list[str], b: list[str]) -> list[tuple[int, int]]:
    """Index pairs of a longest common subsequence of two key lists."""
    n, m = len(a), len(b)
    dp = [[0] * (m + 1) for _ in range(n + 1)]
    for i in range(n - 1, -1, -1):
        for j in range(m - 1, -1, -1):
            dp[i][j] = dp[i + 1][j + 1] + 1 if a[i] == b[j] else max(dp[i + 1][j], dp[i][j + 1])
    pairs, i, j = [], 0, 0
    while i < n and j < m:
        if a[i] == b[j]:
            pairs.append((i, j))
            i, j = i + 1, j + 1
        elif dp[i + 1][j] >= dp[i][j + 1]:
            i += 1
        else:
            j += 1
    return pairs


def diff_cassettes(
    base: Cassette,
    new: Cassette,
    *,
    ignore_args: list[str] | None = None,
    tolerance: Tolerance = "normalized",
    fail_on: list[str] | tuple[str, ...] = DEFAULT_FAIL_ON,
) -> TrajectoryDiff:
    ignore = ignore_args or []

    def key(s: ToolStep) -> str:
        return f"{s.server}\x00{s.name}\x00{args_key(s.args, ignore_args=ignore, tolerance=tolerance)}"

    a, b = base.tool_steps(), new.tool_steps()
    pairs = _lcs_pairs([key(s) for s in a], [key(s) for s in b])
    entries: list[DiffEntry] = []
    i = j = 0
    for pi, pj in [*pairs, (len(a), len(b))]:
        entries += _gap(a[i:pi], b[j:pj])
        if pi < len(a):
            same = dumps(normalize(a[pi].result)) == dumps(normalize(b[pj].result))
            entries.append(DiffEntry("same" if same else "result_changed", a[pi], b[pj]))
        i, j = pi + 1, pj + 1

    counts: dict[str, int] = {}
    for e in entries:
        counts[e.kind] = counts.get(e.kind, 0) + 1
    return TrajectoryDiff(
        entries=entries,
        output_similarity=output_similarity(base.output, new.output),
        base_totals=_totals(base),
        new_totals=_totals(new),
        fail_on=tuple(fail_on),
        counts=counts,
    )


def _gap(removed: list[ToolStep], added: list[ToolStep]) -> list[DiffEntry]:
    """Between two matched calls: removed/added calls to one tool pair up as an args change; the rest add/remove."""
    out: list[DiffEntry] = []
    free = list(added)
    leftover_removed: list[ToolStep] = []
    for r in removed:
        mate = next((x for x in free if x.server == r.server and x.name == r.name), None)
        if mate is not None:
            free.remove(mate)
            out.append(DiffEntry("tool_args_changed", r, mate))
        else:
            leftover_removed.append(r)
    out += [DiffEntry("tool_removed", base=r) for r in leftover_removed]
    out += [DiffEntry("tool_added", new=x) for x in free]
    return out
