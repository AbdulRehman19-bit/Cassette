from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from ..trace import TraceEvent
from .schema import CASSETTE_VERSION, Cassette


def _present(**kw: Any) -> dict[str, Any]:
    """Drop None values so optional fields stay absent in the file rather than null."""
    return {k: v for k, v in kw.items() if v is not None}


def build_cassette(
    events: list[TraceEvent],
    *,
    scenario: str,
    input: dict[str, Any],  # noqa: A002
    output: str,
    agent: dict[str, Any] | None = None,
    recorded_at: str | None = None,
) -> Cassette:
    """Fold a run's trace into a cassette: model/tool events become ordered steps; tool listings become toolSchemas."""
    steps: list[dict[str, Any]] = []
    tool_schemas: dict[str, Any] = {}
    for ev in events:
        kind = ev.get("type")
        if kind == "model":
            steps.append(
                _present(
                    i=len(steps),
                    type="model",
                    request=ev.get("request"),
                    response=ev.get("response"),
                    usage=ev.get("usage"),
                    ms=ev.get("ms"),
                )
            )
        elif kind == "divergence":
            # The agent made a call the cassette had no answer for; keep it in the trajectory so the diff sees it.
            steps.append(
                _present(
                    i=len(steps),
                    type="tool",
                    server=ev["server"],
                    name=ev["name"],
                    args=ev.get("args") or {},
                    result={"content": [{"type": "text", "text": ev.get("reason", "")}], "isError": True},
                    isError=True,
                )
            )
        elif kind == "tool":
            steps.append(
                _present(
                    i=len(steps),
                    type="tool",
                    server=ev["server"],
                    name=ev["name"],
                    args=ev.get("args") or {},
                    result=ev.get("result"),
                    isError=ev.get("isError") or None,
                    ms=ev.get("ms"),
                )
            )
        elif kind == "tools":
            tool_schemas[ev["server"]] = ev["tools"]  # latest listing wins
    return Cassette.model_validate(
        {
            "version": CASSETTE_VERSION,
            "scenario": scenario,
            "recordedAt": recorded_at or datetime.now(UTC).isoformat(),
            "agent": agent or {},
            "input": input,
            "steps": steps,
            "output": output,
            "toolSchemas": tool_schemas,
        }
    )
