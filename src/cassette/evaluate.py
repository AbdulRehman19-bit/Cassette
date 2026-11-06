"""Judge one replayed scenario: trajectory diff + assertions + run health. Shared by `cassette test` and the report."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .assertions import AssertionContext, AssertionResult, run_assertions, run_cost_usd
from .cassette import Cassette
from .config import Config
from .differ import TrajectoryDiff, diff_cassettes
from .runner import ScenarioRun


@dataclass
class ScenarioResult:
    name: str
    base: Cassette
    new: Cassette
    diff: TrajectoryDiff
    checks: list[AssertionResult]
    agent_exit_code: int
    divergences: list[dict[str, Any]] = field(default_factory=list)
    offline: bool = False
    attack: bool = False
    base_cost_usd: float | None = None
    new_cost_usd: float | None = None

    @property
    def output_broke(self) -> bool:
        # Offline replays every recorded model turn, so the output must reproduce exactly.
        return self.offline and not self.diff.output_same

    @property
    def ok(self) -> bool:
        return self.agent_exit_code == 0 and self.diff.ok and not self.output_broke and all(c.ok for c in self.checks)


def evaluate_scenario(
    cfg: Config,
    name: str,
    base: Cassette,
    run: ScenarioRun,
    *,
    offline: bool = False,
    live_schemas: dict[str, list[dict[str, Any]]] | None = None,
) -> ScenarioResult:
    scenario = cfg.scenario(name)
    d = diff_cassettes(
        base,
        run.cassette,
        ignore_args=cfg.diff.ignoreArgs,
        tolerance=cfg.diff.tolerance,
        fail_on=cfg.diff.failOn,
    )
    ctx = AssertionContext(
        cassette=run.cassette, baseline=base, root=cfg.root, pricing=cfg.pricing, live_schemas=live_schemas
    )
    base_ctx = AssertionContext(cassette=base, pricing=cfg.pricing)
    return ScenarioResult(
        name=name,
        base=base,
        new=run.cassette,
        diff=d,
        checks=run_assertions([*cfg.assertions, *scenario.assertions], ctx),
        agent_exit_code=run.exit_code,
        divergences=run.divergences,
        offline=offline,
        attack=scenario.attack,
        base_cost_usd=run_cost_usd(base_ctx),
        new_cost_usd=run_cost_usd(ctx),
    )
