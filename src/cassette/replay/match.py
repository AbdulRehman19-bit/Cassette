"""Finds the recorded tool result for a live call."""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, Literal

from ..cassette import Cassette, ToolStep, canonical_args, dumps, normalize

Tolerance = Literal["exact", "normalized"]


def _squash(v: Any) -> Any:
    if isinstance(v, str):
        return re.sub(r"\s+", " ", v.strip())
    if isinstance(v, list):
        return [_squash(x) for x in v]
    if isinstance(v, dict):
        return {k: _squash(x) for k, x in v.items()}
    return v


def loose_args(args: dict[str, Any], ignore: list[str]) -> str:
    """Args with ignored names dropped and whitespace collapsed; the tolerant comparison key."""
    kept = {k: v for k, v in args.items() if k not in ignore}
    return dumps(_squash(normalize(kept)))


def args_key(args: dict[str, Any], *, ignore_args: list[str], tolerance: Tolerance) -> str:
    """The key two calls must share to count as the same call under the configured tolerance."""
    if tolerance == "exact":
        return canonical_args(args)
    return loose_args(args, ignore_args)


@dataclass
class Matcher:
    """Each recorded step answers one call (repeated identical calls replay in order).

    Exact match wins; then the tolerant match; otherwise None, which the caller reports as a divergence.
    """

    cassette: Cassette
    ignore_args: list[str] = field(default_factory=list)
    tolerance: Tolerance = "normalized"
    _steps: list[ToolStep] = field(init=False)
    _used: set[int] = field(init=False, default_factory=set)

    def __post_init__(self) -> None:
        self._steps = self.cassette.tool_steps()

    def find(self, server: str, name: str, args: dict[str, Any]) -> ToolStep | None:
        want = canonical_args(args)
        hit = self._take(lambda s: s.server == server and s.name == name and canonical_args(s.args) == want)
        if hit or self.tolerance == "exact":
            return hit
        want_loose = loose_args(args, self.ignore_args)
        return self._take(
            lambda s: s.server == server and s.name == name and loose_args(s.args, self.ignore_args) == want_loose
        )

    def unused(self) -> list[ToolStep]:
        """Recorded tool steps that were never asked for."""
        return [s for i, s in enumerate(self._steps) if i not in self._used]

    def _take(self, pred: Callable[[ToolStep], bool]) -> ToolStep | None:
        for i, s in enumerate(self._steps):
            if i not in self._used and pred(s):
                self._used.add(i)
                return s
        return None
