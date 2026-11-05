# Cassette — project notes

"pytest for agents": records an AI agent's runs (model + MCP tool calls) into cassette files, replays them in CI, diffs trajectories, asserts rules (incl. prompt-injection), reports as HTML + PR comment. Full spec: `docs/SPEC.pdf`. Plan: `docs/PLAN.md`.

## Goals
Record/replay over MCP (stdio, then Streamable HTTP) · trajectory diff (tools, args, results, output, tokens, cost, latency) · deterministic assertions · static HTML report + PR comment · live ChangelogCat demo agent.

## Non-goals (4 weeks)
No hosted dashboard/DB/auth · no per-provider SDK adapters (MCP is the tool boundary; one thin model wrapper) · ~5 attack fixtures only · no multi-server contract testing · no sandboxed code execution · no LLM-as-judge in core.

## Stack
TypeScript, Node >=22, pnpm workspaces, tsup, Vitest, zod, yaml, commander + picocolors, `@modelcontextprotocol/sdk`, `@anthropic-ai/sdk` (+ `openai` second adapter), `diff`, Preact + Vite (report, single inlined HTML), Changesets.

## Layout
- `packages/core` — proxy, model wrapper, cassette store, matcher, differ, assertions
- `packages/cli` — `cassette` binary (npm package name `cassette-cli`; `cassette` is taken on npm)
- `packages/report` — HTML report + Markdown PR comment
- `action/` — GitHub Action
- `examples/changelogcat` — demo agent, its `cassette.yaml`, `cassettes/`, `attacks/`
- `docs/` — spec, plan

## Determinism rules
Temperature 0 + fixed seed where the provider supports it (the current @anthropic-ai/sdk Messages API exposes no temperature param, so Anthropic runs rely on tolerant matching) · strip/placeholder volatile fields (timestamps, IDs, key order) before diffing · configurable `tolerance` ignores whitespace/key-order arg changes · fail on tool-level changes by default; compare output text by similarity, not equality.

## Run modes
`record` live model+tools · `replay` (CI default) live model + recorded tools · `replay --offline` recorded model + tools.

## Working rules
- Commit and push after every step. Do NOT add Co-Authored-By lines.
- Pin MCP SDK version; keep transport code in one module.
- Fixtures use only placeholder domains (`evil.example`) and fake canaries.
- Never open red-team PRs on others' repos without explicit permission.
- Check: `pnpm lint && pnpm typecheck && pnpm build && pnpm test`.
