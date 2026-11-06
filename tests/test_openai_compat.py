import json
from typing import Any

from cassette.model.openai_compat import AnthropicShapedClient, from_openai_response, to_openai_request

PARAMS: dict[str, Any] = {
    "model": "llama-3.3-70b-versatile",
    "max_tokens": 100,
    "system": "be brief",
    "tools": [{"name": "get_pull_request", "description": "get", "input_schema": {"type": "object"}}],
    "messages": [
        {"role": "user", "content": "go"},
        {
            "role": "assistant",
            "content": [
                {"type": "text", "text": "checking"},
                {"type": "tool_use", "id": "call_1", "name": "get_pull_request", "input": {"number": 7}},
            ],
        },
        {"role": "user", "content": [{"type": "tool_result", "tool_use_id": "call_1", "content": "{}"}]},
    ],
}


def test_request_translation():
    r = to_openai_request(PARAMS)
    assert r["model"] == "llama-3.3-70b-versatile" and r["max_tokens"] == 100
    assert [m["role"] for m in r["messages"]] == ["system", "user", "assistant", "tool"]
    assistant = r["messages"][2]
    assert assistant["content"] == "checking"
    assert assistant["tool_calls"][0]["function"] == {"name": "get_pull_request", "arguments": '{"number": 7}'}
    assert r["messages"][3] == {"role": "tool", "tool_call_id": "call_1", "content": "{}"}
    assert r["tools"][0]["function"]["parameters"] == {"type": "object"}


def test_response_translation_to_anthropic_shape():
    openai_resp = {
        "id": "chatcmpl-1",
        "model": "m",
        "choices": [
            {
                "finish_reason": "tool_calls",
                "message": {
                    "content": None,
                    "tool_calls": [
                        {"id": "call_9", "type": "function", "function": {"name": "t", "arguments": '{"a": 1}'}}
                    ],
                },
            }
        ],
        "usage": {"prompt_tokens": 11, "completion_tokens": 4},
    }
    r = from_openai_response(openai_resp)
    assert r["content"] == [{"type": "tool_use", "id": "call_9", "name": "t", "input": {"a": 1}}]
    assert r["stop_reason"] == "tool_use"
    assert r["usage"] == {"input_tokens": 11, "output_tokens": 4}


def test_text_only_response_and_empty_arguments():
    r = from_openai_response({"choices": [{"finish_reason": "stop", "message": {"content": "## New"}}], "usage": {}})
    assert r["content"] == [{"type": "text", "text": "## New"}] and r["stop_reason"] == "end_turn"
    r = from_openai_response(
        {
            "choices": [
                {
                    "message": {"tool_calls": [{"id": "c", "function": {"name": "t", "arguments": ""}}]},
                    "finish_reason": "tool_calls",
                }
            ]
        }
    )
    assert r["content"][0]["input"] == {}


class FakeOpenAI:
    """Records what it was called with; returns a canned completion."""

    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []
        self.chat = self
        self.completions = self

    async def create(self, **kw: Any) -> dict[str, Any]:
        self.calls.append(kw)
        return {"choices": [{"finish_reason": "stop", "message": {"content": "ok"}}], "usage": {}}


async def test_client_sends_deterministic_settings_and_returns_anthropic_shape():
    fake = FakeOpenAI()
    res = await AnthropicShapedClient(fake).messages.create(**PARAMS)
    assert res["content"][0]["text"] == "ok"
    assert fake.calls[0]["temperature"] == 0 and fake.calls[0]["seed"] == 0
    json.dumps(res)  # stays JSON-serializable for the trace
