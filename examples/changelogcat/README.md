# ChangelogCat

A small, **read-only** agent that turns the PRs merged between two tags into user-facing release notes. It is the live
test subject for [Cassette](../../README.md).

- `changelogcat/`: the agent (tool loop, result compaction, link filter, previous-tag detection)
- `readonly_github_mcp/`: a GET-only GitHub MCP server exposing exactly `list_pull_requests`, `get_pull_request`,
  `get_pull_request_diff`, `get_file_contents` (`list_pull_requests` also takes `from_ref`/`to_ref` to list only the PRs
  shipped between two tags)
- `cassette.yaml`, `cassettes/`: Cassette scenarios and recorded baselines (real releases of `pallets/click`)
- `action.yml`, `publish/action.yml`: the GitHub Actions used by installed repos; the site in [`docs/`](../../docs/index.html) shows how to add it

## Run it

```bash
export GROQ_API_KEY=... GITHUB_TOKEN=...      # a read-only token is enough
PROVIDER=groq python -m changelogcat pallets/click 8.1.7 8.1.8
```

## Defense in depth

| Layer | What it stops |
|---|---|
| Read-only token and a GET-only server with four tools | any write, even if the model is hijacked |
| Tool allowlist in the agent | calls to tools outside the four |
| Link filter on the output | links that don't point into the repo reaching a release |
| Separate `publish` job (no agent code, no model key) | the agent ever holding write access |
| Cassette assertions in CI (`forbid_tool`, `no_canary`, `links_allowlist`) | a later change weakening any of the above |

## Test it with Cassette

```bash
cassette test --offline          # replay the baselines: no keys, no network
cassette test --model openai/gpt-oss-20b   # what would a smaller model change?
```
