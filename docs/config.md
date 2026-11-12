# cassette.yaml reference

Unknown keys are rejected at load time, so a typo fails loudly instead of being ignored.
`${NAME}` in a string is expanded from the environment (and from a `.env` file found in the config's folder, its
parents, or the current directory; variables already set win).

```yaml
agent:      { command: ..., env: {...} }
servers:    { <name>: { command, args, env } }
scenarios:  [ { name, input, assertions, attack } ]
cassettesDir: cassettes
diff:       { ignoreArgs, failOn, tolerance }
assertions: [ ... ]
pricing:    { <model>: [input_usd_per_mtok, output_usd_per_mtok] }
```

## agent
| Key | Meaning |
|---|---|
| `command` | Shell command that runs your agent. Required. |
| `env` | Extra environment variables for the agent process. |

Cassette starts the agent with `MCP_<SERVER>_COMMAND` and `MCP_<SERVER>_ARGS` (a JSON array) pointing at its proxy,
plus `CASSETTE_TRACE` for the shared trace. Your agent connects to those instead of the real server, and calls
`maybe_wrap_model(client)` so model calls are recorded too.

## servers
Keyed by name; the name upper-cased becomes `<SERVER>` above.

| Key | Meaning |
|---|---|
| `transport` | `stdio` (the only one for now). |
| `command` | Command to start the real server. If `args` is omitted it is split on whitespace. |
| `args` | Explicit argument list (use this when paths contain spaces). |
| `env` | Environment for the server, e.g. `{ GITHUB_TOKEN: "${GITHUB_TOKEN}" }`. |

The real server's command and env reach the proxy through a temporary spec file, never on a command line.

## scenarios
| Key | Meaning |
|---|---|
| `name` | Letters, digits, `.`, `_`, `-`. Names the cassette file. |
| `input` | Free-form mapping. String values become env vars (`repo` -> `REPO`, `fromTag` -> `FROM_TAG`); the whole mapping is also in `CASSETTE_INPUT` as JSON. |
| `input.fixture` | Path to an [attack fixture](attacks.md), applied in `record` mode only. |
| `assertions` | Extra assertions for this scenario, on top of the global ones. |
| `attack` | `true` marks an adversarial scenario; a failure counts as an attack caught in the report. |

## diff
| Key | Default | Meaning |
|---|---|---|
| `failOn` | `tool_added`, `tool_removed`, `tool_args_changed` | Change kinds that fail the run. Also available: `result_changed`. |
| `ignoreArgs` | `[]` | Argument names ignored when matching and comparing calls (e.g. a request id). |
| `tolerance` | `normalized` | `normalized` ignores whitespace and key order in args; `exact` does not. |

Output text is compared by similarity, never equality, so a reworded answer is reported but does not fail the run by
itself.

## assertions
A list of single-key mappings, global at the top level and optionally per scenario. All 11 checks are documented in
[assertions.md](assertions.md).

## pricing
USD per million tokens as `[input, output]`. Overrides or extends the built-in table used by `max_cost_usd`; a model
with no known price makes that assertion fail loudly rather than pass silently.

## cassettesDir
Where cassettes are stored, relative to the config file. Default `cassettes`.

## Run modes
| Command | Model | Tools |
|---|---|---|
| `cassette record` | live | live |
| `cassette test` | live | recorded |
| `cassette test --offline` | recorded | recorded |

`--offline` is deterministic and free, so it is the CI default. Use live-model replay when you want a prompt or model
change to actually take effect.
