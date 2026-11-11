"""Attack fixtures: plant hostile content in what an agent's tools return, while recording.

A fixture is a small JSON file. The proxy applies it on top of the *live* tool results in record mode, so the cassette
captures how the real model reacted to the poisoned input and then replays deterministically like any other cassette.

    {
      "description": "PR body hides an instruction in an HTML comment",
      "patches":   [{"tool": "list_pull_requests", "append_json": {"number": 9001, "title": "..."}}],
      "responses": [{"tool": "get_pull_request", "args": {"pull_number": 9001}, "text": "{...}"}]
    }

- `patches`: after a matching tool returns, if its text result is a JSON array, append the given object(s).
- `responses`: answer a call with fixed text instead of calling the real tool, when every listed arg matches
  (numbers and strings compare as text, so `9001` matches `"9001"`).
Fixtures must only use placeholder domains (`*.example`) and fake canary values, never real malicious URLs or secrets.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from .backend_types import CallResult, ToolBackend, ToolInfo


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Patch(_Model):
    tool: str
    append_json: dict[str, Any] | list[dict[str, Any]]


class Response(_Model):
    tool: str
    args: dict[str, Any] = Field(default_factory=dict)
    text: str


class Fixture(_Model):
    description: str = ""
    # Which assertion is expected to catch this attack (documentation only).
    catches: str = ""
    patches: list[Patch] = Field(default_factory=list)
    responses: list[Response] = Field(default_factory=list)


def load_fixture(path: str | Path) -> Fixture:
    return Fixture.model_validate_json(Path(path).read_text(encoding="utf-8"))


def _args_match(want: dict[str, Any], got: dict[str, Any]) -> bool:
    return all(k in got and str(got[k]) == str(v) for k, v in want.items())


def _text_result(text: str) -> CallResult:
    return {"content": [{"type": "text", "text": text}]}


class InjectingBackend:
    """Wraps a backend and plants the fixture's content in its results."""

    def __init__(self, backend: ToolBackend, fixture: Fixture) -> None:
        self._backend = backend
        self._fixture = fixture

    async def list_tools(self) -> list[ToolInfo]:
        return await self._backend.list_tools()

    async def call_tool(self, name: str, args: dict[str, Any]) -> CallResult:
        for r in self._fixture.responses:
            if r.tool == name and _args_match(r.args, args):
                return _text_result(r.text)
        result = await self._backend.call_tool(name, args)
        for p in (p for p in self._fixture.patches if p.tool == name):
            result = _append_json(result, p.append_json)
        return result


def _append_json(result: CallResult, extra: dict[str, Any] | list[dict[str, Any]]) -> CallResult:
    content = list(result.get("content") or [])
    for i, block in enumerate(content):
        if block.get("type") != "text":
            continue
        try:
            data = json.loads(block["text"])
        except (ValueError, KeyError):
            continue
        if isinstance(data, list):
            data += extra if isinstance(extra, list) else [extra]
            content[i] = {**block, "text": json.dumps(data, ensure_ascii=False)}
            return {**result, "content": content}
    return result
