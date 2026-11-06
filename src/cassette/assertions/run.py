from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .checks import CHECKS, AssertionContext, Failure


@dataclass
class AssertionResult:
    name: str
    arg: Any
    failures: list[Failure] = field(default_factory=list)
    skipped: str | None = None
    error: str | None = None  # the check itself crashed (e.g. a broken custom function)

    @property
    def ok(self) -> bool:
        return not self.failures and self.error is None


def validate_assertions(specs: list[dict[str, Any]]) -> list[tuple[str, Any]]:
    """Each entry is a one-key mapping `{name: argument}`. Unknown names fail loudly so typos never pass silently."""
    out: list[tuple[str, Any]] = []
    for spec in specs:
        if len(spec) != 1:
            raise ValueError(f"each assertion must have exactly one key, got {sorted(spec)}")
        ((name, arg),) = spec.items()
        if name not in CHECKS:
            raise ValueError(f"unknown assertion {name!r}; available: {', '.join(sorted(CHECKS))}")
        out.append((name, arg))
    return out


def run_assertions(specs: list[dict[str, Any]], ctx: AssertionContext) -> list[AssertionResult]:
    results: list[AssertionResult] = []
    for name, arg in validate_assertions(specs):
        try:
            outcome = CHECKS[name](arg, ctx)
        except Exception as e:  # a crashing check must fail the run, not hide behind a pass
            results.append(AssertionResult(name, arg, error=f"{type(e).__name__}: {e}"))
            continue
        results.append(AssertionResult(name, arg, outcome.failures, outcome.skipped))
    return results
