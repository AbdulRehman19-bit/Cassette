import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from changelogcat import run_agent  # noqa: E402


class Host:
    def __init__(self) -> None:
        self.calls: list[str] = []

    async def list_tools(self) -> list[dict[str, Any]]:
        return [
            {"name": "list_pull_requests", "inputSchema": {"type": "object"}},
            {"name": "create_issue", "inputSchema": {"type": "object"}},
        ]

    async def call_tool(self, name: str, args: dict[str, Any]) -> str:
        self.calls.append(name)
        return "[]"


class Scripted:
    """A model that replays a fixed list of responses."""

    def __init__(self, responses: list[dict[str, Any]]) -> None:
        self._r = iter(responses)
        self.messages = self

    async def create(self, **_: Any) -> dict[str, Any]:
        return next(self._r)


def use(name: str, **inp: Any) -> dict[str, Any]:
    return {"content": [{"type": "tool_use", "id": "t1", "name": name, "input": inp}]}


def text(t: str) -> dict[str, Any]:
    return {"content": [{"type": "text", "text": t}]}


async def test_calls_an_allowed_tool_then_returns_the_final_text() -> None:
    host = Host()
    client = Scripted([use("list_pull_requests", state="closed"), text("## New\n- thing")])
    r = await run_agent("a/b", "v1", "v2", host=host, client=client, model="m")
    assert host.calls == ["list_pull_requests"]
    assert r.output == "## New\n- thing"
    assert not r.stopped_by_limit


async def test_refuses_tools_outside_the_allowlist() -> None:
    host = Host()
    client = Scripted([use("create_issue"), text("done")])
    await run_agent("a/b", "v1", "v2", host=host, client=client, model="m")
    assert host.calls == []


async def test_stops_at_the_step_limit() -> None:
    client = Scripted([use("list_pull_requests")] * 20)
    r = await run_agent("a/b", "v1", "v2", host=Host(), client=client, model="m", max_steps=3)
    assert r.stopped_by_limit
    assert r.steps == 3
