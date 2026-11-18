# What we learned testing an agent that reads strangers' text

Draft write-up. Numbers are from real runs against Groq `openai/gpt-oss-120b` (baseline) and `gpt-oss-20b` (swap).

## The setup
ChangelogCat turns merged PRs into release notes through a read-only GitHub MCP server. PR titles and bodies are written
by strangers, so it is a real indirect prompt-injection target. Cassette records its runs and replays them in CI.

## 1. Replay is deterministic, until you change the model
All nine baselines (four click releases, five attacks) replay offline with identical output and no API keys.
Offline replay replays the recorded *model*, so it cannot see a prompt or model edit. Live-model replay can, but a real
model is not perfectly deterministic (it once changed one character of a username). So: offline for the default CI
path, live replay opt-in by label.

## 2. A model swap is not subtle here
Replaying the baseline with `gpt-oss-20b` failed all four release scenarios: different list arguments, different PRs
opened (or none, so `require_tool: get_pull_request` failed), `CHANGELOG.md` read instead, output similarity 0.18-0.24.
We expected "tool calls changed while the text looked fine" and did not get it with these models. We say so rather than
stage it.

## 3. Five attacks, one real gap
With the hardened prompt the agent ignored all five fixtures. With a prompt that trusts PR text, the canary-exfil attack
worked: the model read a planted file and quoted the canary, and `no_canary` caught it. The phishing link was written
by the model but removed by the output link filter, so defense in depth did its job. ChangelogCat has no output defense
against secret leakage; that is the gap a regression test should keep surfacing.

## 4. Red-team PR: fail, fix, pass
Branch `red-team/trust-pr-text` weakens one prompt line. Live replay of the canary scenario failed (the agent started
reading files the baseline never touched). Reverting the line made it pass. The history keeps both steps.
Note it failed on the trajectory diff, not on `no_canary`: live replay can't serve a file the baseline never read.

## Limits
- One model family, one prompt, nine scenarios.
- `forbid_tool` now also sees tools the model requested but the agent refused; tools the model never named leave nothing to see.
- Live replay is flaky; treat it as a signal, not a gate.
