# Cassette — Phased Plan

Source: `Cassette — Project Spec.pdf` (4 weeks, ~20 working days). **Backend switched from TypeScript to Python on 2026-11-06** — wherever the spec names TS tooling, read the Python equivalent in `CLAUDE.md` (uv, pytest, click, pydantic, `mcp` Python SDK; report is a Python-generated single HTML file). Each phase ends at a gate. If a gate slips, cut stretch items, never the week-4 proof PRs.

**Done =** published on npm, runs as a GitHub Action, and has caught one model-swap regression and one injection attack in public PRs on a live ChangelogCat.

---

## Phase 0 — Setup and decisions (before Day 1)
- Save the spec as `docs/SPEC.md`.
- Decide open items (see "Open questions" below).
- Create GitHub repo, npm name check (`cassette`), Anthropic API key, a read-only GitHub token for the agent.

## Phase 1 — Scaffold + ChangelogCat v0 (Days 1–2) — DONE (ported to Python)
- uv + hatchling, pytest, ruff, mypy, CI (ubuntu+windows, py3.11+3.13).
- Layout: `packages/{core,cli,report}`, `action/`, `examples/changelogcat/`, `docs/`.
- `CLAUDE.md` (goals, non-goals, stack, layout, determinism rules).
- ChangelogCat v0: Anthropic SDK loop, GitHub MCP (stdio), read-only tools (`list_pull_requests`, `get_pull_request`, `get_pull_request_diff`, `get_file_contents`), max 12 steps, Markdown output.
- **Gate:** ChangelogCat produces release notes locally on one repo.

## Phase 2 — Record (Days 2–4) — DONE
- MCP proxy, record mode (stdio): forwards and logs (`core/src/proxy`).
- Model wrapper: logs request, response, tokens, latency (`core/src/model`).
- Cassette schema (zod), store, normalization of volatile fields: timestamps, IDs, key order (`core/src/cassette`).
- Capture `toolSchemas` at record time.

## Phase 3 — Replay + CLI core (Days 4–5) — DONE except 3 real baselines (needs tokens)
- Replay mode with the exact-args matcher; unmatched calls are reported as divergence.
- `cassette record`, `cassette test`; `cassette.yaml` config (yaml + zod).
- Record 3 real releases as baselines.
- **Gate (Week 1):** replaying a recorded run makes zero live tool calls and reaches the same final output. Replaying twice gives the same result.

## Phase 4 — Diff (Days 6–7) — DONE
- Sequence alignment on tool name + args; added, removed, changed steps.
- `ignoreArgs`, `tolerance`, `failOn`; output similarity for text.
- Terminal diff output; `cassette diff <a> <b>`.

## Phase 5 — Assertions (Days 8–9) — DONE (docs/assertions.md)
- Day 8: `forbid_tool`, `require_tool`, `no_canary`, `links_allowlist`, budgets (`max_steps`, `max_cost_usd`, `max_latency_ms`).
- Day 9: `tool_sequence`, `output_matches`, `schema_unchanged`, `custom`.
- Deterministic only; no LLM judge.

## Phase 6 — Report + flags (Days 9–10) — DONE (HTML report, PR comment, update, report; gate needs a real smaller-model run)
- Static HTML report (Preact + Vite, inlined single file): per-scenario cards, side-by-side trajectory, highlighted divergence, expandable args/results, output diff, token/cost/latency deltas.
- `cassette update`, `cassette report`, `--offline` (recorded model), `--model`, `--json`, `--filter`.
- **Gate (Week 2):** `--model` set to a smaller model shows a readable trajectory diff in terminal and HTML.

## Phase 7 — GitHub Action + PR comment (Days 11–12) — built; first real PR run pending
- `action/` wrapper around `cassette test`; PR comment markdown (summary line, scenario table, first diverging step, report artifact link); check status.
- Run it on the Cassette repo itself, using `--offline` cassettes for its own tests.

## Phase 8 — ChangelogCat live (Days 12–13) — built; needs GROQ_API_KEY secret + Pages enabled + a real tag push
- Tag-push workflow in installed repos; writes the Release body in a separate narrow-scope step (agent stays read-only).
- One-page install site (GitHub Pages).
- Defenses: read-only token, tool allowlist, post-processing link filter.

## Phase 9 — Attack fixtures (Days 13–14) — DONE (docs/attacks.md)
- 5 fixtures in `attacks/*.json`: `hidden-instruction`, `phishing-link`, `canary-exfil`, `tool-arg-smuggling`, `step-bomb` (placeholder domains and fake canaries only).
- Scenarios + assertions that catch each one.

## Phase 10 — Installs + HTTP (Days 14–15)
- Added: `live-attacks` job in cassette.yml (label `red-team`/`live-replay`) for live-model replay of the injection scenarios.
- Install on own repos + at least 3 others (with opt-in); record their releases.
- Streamable HTTP transport for the proxy (if time; isolate transport code in one module).
- **Gate (Week 3):** a PR on the Cassette repo gets an automatic comment; ChangelogCat has written at least one real release.

## Phase 11 — Public proof PRs (Days 16–17)
- **PR #1:** switch ChangelogCat's model; Cassette flags changed tool calls while output looks fine; write up what and why.
- **PR #2:** `[red-team]` PR on one of your own repos (labelled, with note); Cassette fails; fix prompt/link filter; Cassette passes. Keep fail → fix → pass in commit history.

## Phase 12 — Docs and launch (Days 18–20)
- README updated for attacks + live replay (on `docs/readme`); `cassette-cli` is free on PyPI.
- README (one-line pitch, failing-PR GIF, 3-command quick start, architecture diagram), config and assertion docs.
- Publish to npm (Changesets) and the Action Marketplace; 2-minute demo video.
- Write-up post; launch (Show HN, r/LocalLLaMA / r/MachineLearning, X/LinkedIn).
- **Gate (Week 4):** every success criterion in the spec ticked.

## Stretch (only after Phase 12)
mcpact mode, trajectory viewer, Python agent support, community attack fixtures, ChangelogCat on 10+ repos / as a GitHub App.

---

## Success-criteria checklist
- [ ] `npx cassette record` and `npx cassette test` work on a fresh clone in under 5 min
- [ ] 10+ cassettes replay in under 60 s with zero live tool calls
- [ ] Same replay twice gives the same result (no flaky diffs)
- [ ] Public PR #1 (model swap) fails the check
- [ ] Public PR #2 (red-team) fails the check
- [ ] ChangelogCat installed on your repos + at least 3 others
- [ ] README, write-up, 2-min demo video published

## Top risks to watch
- Non-deterministic diffs → temp 0, normalize args, `ignoreArgs`, fail on tool-level changes only.
- Reads as a promptfoo clone → lead with trajectories and MCP.
- Scope creep → no server/accounts; stretch only after Phase 12.
- Calls missing from cassette → report as divergence; optional live fall-through in record mode.

## Open questions (spec leaves these open; resolve in Phase 0)
1. Cassette `npm` package name: `cassette` may be taken. Scoped name?
2. Model IDs for the baseline and the swap (spec examples: Sonnet → Haiku; use current Claude 5 family).
3. Which repos will ChangelogCat be installed on (yours + 3 others)?
4. Is the OpenAI adapter in scope for the first pass or deferred until the model-swap demo needs it?
5. Output similarity metric for "looks fine" (e.g. normalized text or embedding-free token similarity).
