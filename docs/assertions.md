# Assertions

Assertions are deterministic checks on a run's trajectory and output. There is no LLM-as-judge. They run on every
`cassette test` (including `--offline`) and any failure makes the command exit 1.

Each entry is a one-key mapping `{name: argument}`. Put them under top-level `assertions:` (all scenarios) or under a
scenario's own `assertions:` (that scenario only, added to the global ones). A misspelled name stops the run.

| Assertion | Argument | Fails when |
|---|---|---|
| `forbid_tool` | name or list of globs | the agent calls a matching tool (reports the step) |
| `require_tool` | name or list | a listed tool is never called |
| `tool_sequence` | list of globs; `*` = any run of calls (even none) | the ordered tool names don't match |
| `no_canary` | string or list | the string appears in the final output **or any tool argument** |
| `links_allowlist` | list of `host/path` globs (`github.com/acme/*`; a bare host also allows its sub-paths) | a URL in the output or tool arguments isn't allowed |
| `max_steps` | int | the agent used more model turns than this |
| `max_cost_usd` | number | token cost exceeds it (see pricing below) |
| `max_latency_ms` | number | summed step latency exceeds it |
| `output_matches` | regex, `{regex: ...}`, or `{json_schema: {...}}` | the output fails the regex / isn't valid JSON for the schema |
| `schema_unchanged` | `true` | a live server's tool schemas differ from the recorded ones (needs `--check-schemas`) |
| `custom` | `file.py:function` or `pkg.mod:function` | your function returns `False`, a string, or a list of strings |

`no_canary` and `links_allowlist` look at what the agent *sent out* (output and tool arguments), not at tool
*results*, which legitimately contain whatever the outside world returned.

## Cost

`max_cost_usd` multiplies recorded token usage by a per-model price. The built-in table is a rough default, not a
price list; override or extend it, in USD per million tokens `[input, output]`:

```yaml
pricing:
  openai/gpt-oss-120b: [0.15, 0.60]
```

A model with no known price fails the assertion loudly instead of guessing.

## Schema drift

In replay the proxy serves tool schemas from the cassette, so drift can't show up by itself. `cassette test
--check-schemas` additionally starts each real server, lists its tools (it never calls them) and compares the schemas.
Without the flag `schema_unchanged` is reported as skipped, not passed.

## Custom assertions

```python
# checks.py
def no_dotenv(ctx):                      # ctx.cassette, ctx.baseline, ctx.tools, ctx.root
    return [f"reads .env at step {s.i}" for s in ctx.tools if ".env" in str(s.args)]
```

```yaml
assertions:
  - custom: checks.py:no_dotenv          # path is relative to cassette.yaml
```

Return `None`/`True` to pass; `False`, a string, or a list of strings to fail. A check that raises fails the run.
