"""Use any OpenAI-compatible API (Groq, OpenAI, ...) from an agent written against the Anthropic Messages shape.

The agent keeps calling `client.messages.create(model=, system=, tools=, messages=, max_tokens=)` and gets an
Anthropic-shaped response back, so cassettes have one model-step format no matter which provider produced them and
`--offline` replay works the same for all of them.
"""

from __future__ import annotations

import json
from typing import Any

from .wrap import jsonable

GROQ_BASE_URL = "https://api.groq.com/openai/v1"

_STOP = {"stop": "end_turn", "length": "max_tokens", "tool_calls": "tool_use"}


def to_openai_request(params: dict[str, Any]) -> dict[str, Any]:
    """Anthropic Messages params -> OpenAI chat.completions params."""
    messages: list[dict[str, Any]] = []
    if system := params.get("system"):
        messages.append({"role": "system", "content": system})
    for m in params["messages"]:
        content = m["content"]
        if isinstance(content, str):
            messages.append({"role": m["role"], "content": content})
        elif m["role"] == "assistant":
            text = "".join(b["text"] for b in content if b["type"] == "text")
            calls = [
                {
                    "id": b["id"],
                    "type": "function",
                    "function": {"name": b["name"], "arguments": json.dumps(b.get("input") or {})},
                }
                for b in content
                if b["type"] == "tool_use"
            ]
            msg: dict[str, Any] = {"role": "assistant", "content": text or None}
            if calls:
                msg["tool_calls"] = calls
            messages.append(msg)
        else:  # user turn made of tool_result / text blocks
            for b in content:
                if b["type"] == "tool_result":
                    out = b["content"]
                    if not isinstance(out, str):
                        out = "".join(x.get("text", "") for x in out)
                    messages.append({"role": "tool", "tool_call_id": b["tool_use_id"], "content": out})
                elif b["type"] == "text":
                    messages.append({"role": "user", "content": b["text"]})
    req: dict[str, Any] = {"model": params["model"], "messages": messages}
    if tools := params.get("tools"):
        req["tools"] = [
            {
                "type": "function",
                "function": {
                    "name": t["name"],
                    "description": t.get("description", ""),
                    "parameters": t.get("input_schema") or {"type": "object", "properties": {}},
                },
            }
            for t in tools
        ]
    choice = (params.get("tool_choice") or {}).get("type")
    if choice in ("none", "auto") and req.get("tools"):
        req["tool_choice"] = choice
    if "max_tokens" in params:
        req["max_tokens"] = params["max_tokens"]
    return req


def from_openai_response(resp: dict[str, Any]) -> dict[str, Any]:
    """OpenAI chat.completions response -> Anthropic Message-shaped dict."""
    choice = resp["choices"][0]
    msg = choice["message"]
    content: list[dict[str, Any]] = []
    if msg.get("content"):
        content.append({"type": "text", "text": msg["content"]})
    for call in msg.get("tool_calls") or []:
        fn = call["function"]
        content.append(
            {"type": "tool_use", "id": call["id"], "name": fn["name"], "input": json.loads(fn.get("arguments") or "{}")}
        )
    usage = resp.get("usage") or {}
    return {
        "id": resp.get("id", ""),
        "type": "message",
        "role": "assistant",
        "model": resp.get("model", ""),
        "content": content,
        "stop_reason": _STOP.get(choice.get("finish_reason") or "stop", "end_turn"),
        "stop_sequence": None,
        "usage": {"input_tokens": usage.get("prompt_tokens", 0), "output_tokens": usage.get("completion_tokens", 0)},
    }


class _Messages:
    def __init__(self, client: Any, extra: dict[str, Any]) -> None:
        self._client = client
        self._extra = extra

    async def create(self, **params: Any) -> dict[str, Any]:
        resp = await self._client.chat.completions.create(**to_openai_request(params), **self._extra)
        return from_openai_response(jsonable(resp))


class AnthropicShapedClient:
    """`client.messages.create(...)` backed by an OpenAI-compatible async client."""

    def __init__(self, openai_client: Any, *, temperature: float | None = 0, seed: int | None = 0) -> None:
        extra = {k: v for k, v in {"temperature": temperature, "seed": seed}.items() if v is not None}
        self.messages = _Messages(openai_client, extra)


def groq_client(api_key: str, *, base_url: str = GROQ_BASE_URL) -> AnthropicShapedClient:
    """Groq via its OpenAI-compatible endpoint; temperature 0 and a fixed seed keep replays as stable as it allows."""
    from openai import AsyncOpenAI

    return AnthropicShapedClient(AsyncOpenAI(api_key=api_key, base_url=base_url, max_retries=6))
