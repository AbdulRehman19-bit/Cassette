# Launch post (draft)

**Title:** Cassette: pytest for agents. Record runs, replay in CI, catch behavior changes and prompt injection

I built an agent that writes release notes from merged PRs, then realized I had no way to know when a prompt or model
change quietly altered what it did. Cassette records an agent's runs (model calls and MCP tool calls), replays them in
CI, diffs the trajectory, and runs deterministic assertions such as "never call a write tool", "never emit this
canary", and "only link into this repo".

What it found on its own test subject:
- Replaying with a smaller model changed tool arguments and which PRs were opened; `require_tool` failed.
- A prompt that trusts PR text let a planted secret leak; `no_canary` caught it. The agent had no output defense for
  that. Real gap, found by the tool.
- An output link filter stopped a phishing link the model had written. Defense in depth worked.

Honest limits: one model family, nine scenarios; offline replay replays the recorded model, so prompt edits need
live-model replay, which is not perfectly deterministic.

Repo: https://github.com/AbdulRehman19-bit/Cassette  ·  `pip install cassette-cli` (once published)
Write-up: docs/writeup.md
