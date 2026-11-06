"""Logs (or replays) an agent's model calls. One line in the agent: `client = maybe_wrap_model(Anthropic())`."""

from __future__ import annotations

import inspect
import os
import time
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from ..cassette import Cassette, read_cassette
from ..trace import append_trace

TRACE_ENV = "CASSETTE_TRACE"
REPLAY_MODEL_ENV = "CASSETTE_REPLAY_MODEL"


def jsonable(o: Any) -> Any:
    """SDK response objects (pydantic models) become plain JSON-able data."""
    dump = getattr(o, "model_dump", None)
    if callable(dump):
        return dump(mode="json")
    if isinstance(o, Mapping):
        return {k: jsonable(v) for k, v in o.items()}
    if isinstance(o, list | tuple):
        return [jsonable(v) for v in o]
    return o


class AttrDict(dict[str, Any]):
    """A dict that also reads like an SDK object (`res.content[0].text`), still JSON-serializable."""

    def __getattr__(self, name: str) -> Any:
        try:
            return self[name]
        except KeyError:
            raise AttributeError(name) from None


def attrify(o: Any) -> Any:
    if isinstance(o, dict):
        return AttrDict({k: attrify(v) for k, v in o.items()})
    if isinstance(o, list):
        return [attrify(v) for v in o]
    return o


def _usage(data: Any) -> dict[str, int] | None:
    u = data.get("usage") if isinstance(data, dict) else None
    if not isinstance(u, dict):
        return None
    return {"in": int(u.get("input_tokens") or 0), "out": int(u.get("output_tokens") or 0)}


class _Messages:
    def __init__(self, inner: Any, trace_path: str | Path) -> None:
        self._inner = inner
        self._trace = trace_path

    def __getattr__(self, name: str) -> Any:
        return getattr(self._inner, name)

    def _log(self, kwargs: dict[str, Any], response: Any, start: float) -> None:
        data = jsonable(response)
        event: dict[str, Any] = {
            "type": "model",
            "request": jsonable(kwargs),
            "response": data,
            "ms": round((time.perf_counter() - start) * 1000),
        }
        if (usage := _usage(data)) is not None:
            event["usage"] = usage
        append_trace(self._trace, event)

    def create(self, *args: Any, **kwargs: Any) -> Any:
        start = time.perf_counter()
        res = self._inner.create(*args, **kwargs)
        if inspect.isawaitable(res):  # AsyncAnthropic

            async def finish() -> Any:
                r = await res
                self._log(kwargs, r, start)
                return r

            return finish()
        self._log(kwargs, res, start)
        return res


class _Wrapped:
    def __init__(self, client: Any, trace_path: str | Path) -> None:
        self._client = client
        self.messages = _Messages(client.messages, trace_path)

    def __getattr__(self, name: str) -> Any:
        return getattr(self._client, name)


def wrap_model(client: Any, *, trace_path: str | Path) -> Any:
    """Each `messages.create` call appends request, response, token usage and latency to the trace."""
    return _Wrapped(client, trace_path)


class _ReplayMessages:
    def __init__(self, cassette: Cassette, trace_path: str | Path | None) -> None:
        self._steps = cassette.model_steps()
        self._next = 0
        self._trace = trace_path

    def _answer(self, kwargs: dict[str, Any]) -> Any:
        if self._next >= len(self._steps):
            raise RuntimeError(
                f"cassette: no recorded model response for turn {self._next + 1} (recorded {len(self._steps)})"
            )
        step = self._steps[self._next]
        self._next += 1
        if self._trace:
            event: dict[str, Any] = {
                "type": "model",
                "request": jsonable(kwargs),
                "response": step.response,
            }
            if step.usage:
                event["usage"] = step.usage
            if step.ms is not None:
                event["ms"] = step.ms
            append_trace(self._trace, event)
        return _rehydrate(step.response)

    def create(self, *args: Any, **kwargs: Any) -> Any:
        return self._answer(kwargs)

    async def acreate(self, *args: Any, **kwargs: Any) -> Any:
        return self._answer(kwargs)


def _rehydrate(response: Any) -> Any:
    """Give the agent real SDK types when the SDK is installed; otherwise attribute-readable dicts."""
    try:
        from anthropic.types import Message  # type: ignore[import-not-found,unused-ignore]

        return Message.model_validate(response)
    except Exception:
        return attrify(response)


class _ReplayClient:
    def __init__(self, cassette: Cassette, trace_path: str | Path | None, is_async: bool) -> None:
        msgs = _ReplayMessages(cassette, trace_path)
        self.messages = type("Messages", (), {"create": msgs.acreate if is_async else msgs.create})()


def replay_model(cassette: Cassette, *, trace_path: str | Path | None = None, is_async: bool = False) -> Any:
    """Serves recorded model responses in order; asking for more turns than were recorded fails."""
    return _ReplayClient(cassette, trace_path, is_async)


def maybe_wrap_model(client: Any, env: Mapping[str, str] | None = None) -> Any:
    """Log calls under record|test; serve recorded responses with --offline; else return `client` untouched."""
    e = os.environ if env is None else env
    trace = e.get(TRACE_ENV)
    replay_from = e.get(REPLAY_MODEL_ENV)
    if replay_from:
        return replay_model(
            read_cassette(replay_from), trace_path=trace, is_async=inspect.iscoroutinefunction(client.messages.create)
        )
    return wrap_model(client, trace_path=trace) if trace else client
