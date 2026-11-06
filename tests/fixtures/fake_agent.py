"""A scripted "agent": two tool calls over MCP, then a final answer. The model is a deterministic
fake so the e2e test needs no API key; Cassette wraps it exactly like a real Anthropic client."""

import asyncio
import json
import os
import sys

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import get_default_environment, stdio_client

from cassette.model import jsonable, maybe_wrap_model


class FakeMessages:
    def create(self, **params):
        turn = sum(1 for m in params["messages"] if m["role"] == "assistant")
        usage = {"input_tokens": 10 + turn, "output_tokens": 5}
        seen = json.dumps(params["messages"])
        if (
            os.environ.get("VULNERABLE") == "1"
            and "IGNORE PREVIOUS" in seen
            and "create_issue" not in seen.split("IGNORE PREVIOUS")[0]
            and '"name": "create_issue"' not in seen
        ):
            block = {"type": "tool_use", "id": "toolu_aaaaaaaa9", "name": "create_issue", "input": {"title": "pwned"}}
            return {"id": f"msg_aaaaaaaa{turn}", "type": "message", "role": "assistant", "content": [block],
                    "model": "fake", "stop_reason": "tool_use", "usage": usage}  # fmt: skip
        if turn == 0:
            block = {
                "type": "tool_use",
                "id": "toolu_aaaaaaaa1",
                "name": "list_pull_requests",
                "input": {"state": "closed"},
            }
        elif turn == 1:
            # A "smaller model" reads a file instead of the PR: different behavior, same final text.
            if os.environ.get("MODEL") == "small":
                block = {
                    "type": "tool_use",
                    "id": "toolu_aaaaaaaa2",
                    "name": "get_file_contents",
                    "input": {"path": "CHANGELOG.md"},
                }
            else:
                block = {
                    "type": "tool_use",
                    "id": "toolu_aaaaaaaa2",
                    "name": "get_pull_request",
                    "input": {"number": 7},
                }
        else:
            block = {"type": "text", "text": "## New\n- Dark mode"}
        return {"id": f"msg_aaaaaaaa{turn}", "type": "message", "role": "assistant", "content": [block],
                "model": "fake", "stop_reason": "end_turn", "usage": usage}  # fmt: skip


class FakeClient:
    messages = FakeMessages()


async def main() -> None:
    model = maybe_wrap_model(FakeClient())
    params = StdioServerParameters(
        command=os.environ["MCP_FAKE_COMMAND"],
        args=json.loads(os.environ["MCP_FAKE_ARGS"]),
        env=get_default_environment(),
    )
    async with stdio_client(params) as (read, write), ClientSession(read, write) as session:
        await session.initialize()
        await session.list_tools()
        messages: list[dict] = [{"role": "user", "content": "go"}]
        while True:
            res = jsonable(model.messages.create(messages=messages))
            block = res["content"][0]
            messages.append({"role": "assistant", "content": [dict(block)]})
            if block["type"] != "tool_use":
                sys.stdout.write(block["text"] + "\n")
                return
            out = await session.call_tool(block["name"], block["input"])
            messages.append({"role": "user", "content": [{"type": "tool_result", "tool_use_id": block["id"],
                                                          "content": out.content[0].text}]})  # fmt: skip


asyncio.run(main())
