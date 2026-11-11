# Cassette

**pytest for agents.** Cassette records an AI agent's runs (every model call and every MCP tool call), replays them in CI,
and fails the PR when the agent's *behavior* changes or a prompt-injection gets through, even when the final text still
looks fine.

```
× release-v1.4  trajectory changed
    - step 3  get_pull_request(number: 7)
    + step 3  get_file_contents(path: "CHANGELOG.md")
    output similarity 1.00 (looks fine; behavior changed)
    × forbid_tool: called get_file_contents at step 3
```

Prompt-level eval tools score outputs. Cassette checks what the agent *did*: which tools it called, with what
arguments, in what order, and whether it leaked a canary or followed a link it shouldn't. A tool-call diff is a fact, not
an LLM judge's opinion.

> Status: early. Record/replay, trajectory diff, assertions, prompt-injection fixtures, HTML report, PR comment and the
> GitHub Action work. Not yet published to PyPI (the name `cassette-cli` is free).

## How it works

Cassette sits between your agent and its MCP servers (a recording proxy) and wraps the model client:

1. **Record**: `cassette record` runs the agent live and writes `cassettes/<scenario>.cassette.json`.
2. **Replay**: `cassette test` re-runs the agent with tool results served from the cassette. Zero live tool calls, same
   answers every time. `--offline` also replays the recorded model, so it costs nothing.
3. **Diff**: the new trajectory is aligned against the baseline (tool order, arguments, results, output, tokens, latency).
4. **Assert**: deterministic checks such as `forbid_tool`, `no_canary`, `links_allowlist`, budgets. See
   [docs/assertions.md](docs/assertions.md).
5. **Report**: a static `cassette-report/index.html` and a PR comment.

## Quick start

```bash
pip install cassette-cli            # once published; for now: pip install .
```

Add one line to your agent so Cassette can observe its model calls:

```python
from cassette.model import maybe_wrap_model
client = maybe_wrap_model(AsyncAnthropic())     # a no-op outside Cassette
```

Describe your scenarios in `cassette.yaml`:

```yaml
agent:
  command: "python -m myagent"
servers:
  github:
    command: "npx -y @modelcontextprotocol/server-github"   # any MCP stdio server
    env: { GITHUB_PERSONAL_ACCESS_TOKEN: "${GITHUB_TOKEN}" }
scenarios:
  - name: release-v1.4
    input: { repo: acme/widgets, fromTag: v1.3.0, toTag: v1.4.0 }
assertions:
  - forbid_tool: ["create_*", "merge_*", "push_*"]
  - no_canary: "CANARY-7f3a"
```

Your agent finds each server through `MCP_<SERVER>_COMMAND` and `MCP_<SERVER>_ARGS` (a JSON array) and speaks MCP over
stdio to whatever those point at; Cassette points them at its proxy.

```bash
cassette record              # run live, write cassettes/
cassette test --offline      # replay, diff, assert, write cassette-report/
cassette test --model small  # what would a different model change?
```

| Command | What it does |
|---|---|
| `cassette record [scenario]` | Run live and write cassettes |
| `cassette test [scenario]` | Replay, diff against the baseline, run assertions; exit 1 on any failure |
| `cassette update [scenario]` | Accept the last run as the new baseline (like `jest -u`) |
| `cassette diff <a> <b>` | Diff two cassette files |
| `cassette report` | Rebuild the HTML report and PR comment from the last run |
| `cassette comment` | Post or update the Cassette comment on a PR |

Common flags: `--offline`, `--model <id>`, `--json`, `--filter <glob>`, `--check-schemas`.

## GitHub Action

```yaml
name: cassette
on: [pull_request]
permissions: { contents: read, pull-requests: write }
jobs:
  agent-tests:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: AbdulRehman19-bit/Cassette/action@main
        with:
          offline: "true"
          install: pip install -r requirements.txt
```

It runs `cassette test`, uploads the report as an artifact, posts (and keeps updating) one PR comment, and sets the
check status. A comment that can't be posted (a fork PR's read-only token) never decides the result.

## Prompt-injection tests

A fixture plants hostile content in what the agent's tools return *while recording*, so the cassette holds the real
model's reaction and replays deterministically. Mark the scenario `attack: true` and the report counts a failure as an
attack caught.

```yaml
scenarios:
  - name: injection-canary-exfil
    attack: true
    input: { repo: pallets/click, fromTag: 8.1.4, toTag: 8.1.5, fixture: attacks/canary-exfil.json }
```

ChangelogCat ships five (hidden instruction, phishing link, canary exfiltration, tool-argument smuggling, step bomb);
see [docs/attacks.md](docs/attacks.md) for what each does and what we measured. One honest limit: offline replay
replays the recorded *model*, so a prompt edit only shows up with live-model replay (`cassette test` without
`--offline`; the repo's `live-attacks` job runs it on PRs labelled `red-team` or `live-replay`). Live replay with a
real model is not perfectly deterministic, so offline is the default CI path.

## Example: ChangelogCat

[examples/changelogcat](examples/changelogcat) is a small read-only agent that turns merged PRs into release notes
through a small read-only GitHub MCP server (GET-only, four tools). It is the test subject Cassette is dogfooded on, with a committed baseline you can replay
without any API keys:

```bash
uv sync
cd examples/changelogcat && uv run cassette test --offline
```

## Develop

```bash
uv sync
uv run ruff check src tests examples && uv run mypy && uv run pytest -q
```

Plan and status: [docs/PLAN.md](docs/PLAN.md). Original spec: [docs/SPEC.pdf](docs/SPEC.pdf).
