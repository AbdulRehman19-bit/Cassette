"""The built-in assertions. Every check is deterministic; there is deliberately no LLM-as-judge."""

from __future__ import annotations

import fnmatch
import importlib
import importlib.util
import json
import re
import sys
from collections.abc import Callable
from dataclasses import dataclass, field
from functools import cache
from pathlib import Path
from typing import Any

from ..cassette import Cassette, ToolStep, dumps, normalize
from .pricing import price_for

URL = re.compile(r"https?://[^\s<>\"'\\)\]]+")


@dataclass
class Failure:
    message: str
    step: int | None = None  # cassette step index, when the failure points at one


@dataclass
class AssertionContext:
    cassette: Cassette  # the run under test
    baseline: Cassette | None = None
    root: Path = field(default_factory=Path)
    pricing: dict[str, list[float]] = field(default_factory=dict)
    # Tool schemas read from the live servers (only when probing with --check-schemas).
    live_schemas: dict[str, list[dict[str, Any]]] | None = None

    @property
    def tools(self) -> list[ToolStep]:
        return self.cassette.tool_steps()


@dataclass
class Outcome:
    failures: list[Failure] = field(default_factory=list)
    skipped: str | None = None  # reason the check could not run (not a failure)


Check = Callable[[Any, AssertionContext], Outcome]


def _as_list(arg: Any) -> list[Any]:
    return list(arg) if isinstance(arg, list | tuple) else [arg]


def _fail(*items: Failure) -> Outcome:
    return Outcome(failures=list(items))


OK = Outcome()


def forbid_tool(arg: Any, ctx: AssertionContext) -> Outcome:
    pats = [str(p) for p in _as_list(arg)]
    return _fail(
        *(
            Failure(f"called {s.name} at step {s.i}", s.i)
            for s in ctx.tools
            if any(fnmatch.fnmatchcase(s.name, p) for p in pats)
        )
    )


def require_tool(arg: Any, ctx: AssertionContext) -> Outcome:
    called = {s.name for s in ctx.tools}
    return _fail(*(Failure(f"{p} was never called") for p in map(str, _as_list(arg)) if p not in called))


def tool_sequence(arg: Any, ctx: AssertionContext) -> Outcome:
    """Tool names, in order, must match the pattern. `*` = any run of calls (even none); other items are globs."""
    pats = [str(p) for p in _as_list(arg)]
    names = [s.name for s in ctx.tools]

    @cache
    def match(i: int, j: int) -> bool:
        if i == len(pats):
            return j == len(names)
        if pats[i] == "*":
            return match(i + 1, j) or (j < len(names) and match(i, j + 1))
        return j < len(names) and fnmatch.fnmatchcase(names[j], pats[i]) and match(i + 1, j + 1)

    if match(0, 0):
        return OK
    return _fail(Failure(f"tool calls [{', '.join(names)}] do not match sequence [{', '.join(pats)}]"))


def _searchable(ctx: AssertionContext) -> list[tuple[str, str, int | None]]:
    """(where, text, step) for the final output and every tool call's arguments: what the agent *sent out*."""
    items: list[tuple[str, str, int | None]] = [("output", ctx.cassette.output, None)]
    items += [(f"args of {s.name}", dumps(s.args), s.i) for s in ctx.tools]
    return items


def no_canary(arg: Any, ctx: AssertionContext) -> Outcome:
    out = []
    for canary in map(str, _as_list(arg)):
        for where, text, step in _searchable(ctx):
            if canary in text:
                out.append(Failure(f"canary {canary!r} leaked into {where}", step))
    return _fail(*out)


def _allowed(url: str, patterns: list[str]) -> bool:
    bare = re.sub(r"^https?://", "", url).rstrip("/")
    for p in patterns:
        p = re.sub(r"^https?://", "", p).rstrip("/")
        if fnmatch.fnmatchcase(bare, p) or ("*" not in p and (bare == p or bare.startswith(p + "/"))):
            return True
    return False


def links_allowlist(arg: Any, ctx: AssertionContext) -> Outcome:
    patterns = [str(p) for p in _as_list(arg)]
    out = []
    for where, text, step in _searchable(ctx):
        for url in {u.rstrip(".,;:!?") for u in URL.findall(text)}:
            if not _allowed(url, patterns):
                out.append(Failure(f"link {url} in {where} is not on the allowlist", step))
    return _fail(*sorted(out, key=lambda f: f.message))


def max_steps(arg: Any, ctx: AssertionContext) -> Outcome:
    n = len(ctx.cassette.model_steps())  # one step = one model turn of the agent loop
    return OK if n <= int(arg) else _fail(Failure(f"{n} steps exceeds the limit of {int(arg)}"))


def run_cost_usd(ctx: AssertionContext) -> float | None:
    price = price_for(ctx.cassette.agent.model, ctx.pricing)
    if price is None:
        return None
    tin = sum((m.usage or {}).get("in", 0) for m in ctx.cassette.model_steps())
    tout = sum((m.usage or {}).get("out", 0) for m in ctx.cassette.model_steps())
    return (tin * price[0] + tout * price[1]) / 1_000_000


def max_cost_usd(arg: Any, ctx: AssertionContext) -> Outcome:
    cost = run_cost_usd(ctx)
    if cost is None:
        model = ctx.cassette.agent.model
        return _fail(Failure(f"no pricing for model {model!r}; add it under `pricing:` in cassette.yaml"))
    return OK if cost <= float(arg) else _fail(Failure(f"cost ${cost:.4f} exceeds the budget of ${float(arg):.4f}"))


def max_latency_ms(arg: Any, ctx: AssertionContext) -> Outcome:
    total = sum(s.ms or 0 for s in ctx.cassette.steps)
    return (
        OK
        if total <= float(arg)
        else _fail(Failure(f"latency {total:.0f} ms exceeds the limit of {float(arg):.0f} ms"))
    )


def output_matches(arg: Any, ctx: AssertionContext) -> Outcome:
    """`"regex"` | `{regex: "..."}` | `{json_schema: {...}}` (output must be JSON valid against the schema)."""
    out = ctx.cassette.output
    spec: dict[str, Any] = {"regex": arg} if isinstance(arg, str) else arg
    failures: list[Failure] = []
    if "regex" in spec and not re.search(spec["regex"], out, re.MULTILINE):
        failures.append(Failure(f"output does not match /{spec['regex']}/"))
    if "json_schema" in spec:
        import jsonschema

        try:
            jsonschema.validate(json.loads(out), spec["json_schema"])
        except json.JSONDecodeError:
            failures.append(Failure("output is not valid JSON"))
        except jsonschema.ValidationError as e:
            failures.append(Failure(f"output violates the JSON schema: {e.message}"))
    if not ({"regex", "json_schema"} & set(spec)):
        failures.append(Failure("output_matches needs a regex or json_schema"))
    return _fail(*failures)


def _schemas(c: Cassette | dict[str, list[dict[str, Any]]]) -> dict[str, Any]:
    raw = {k: [t.model_dump() for t in v] for k, v in c.toolSchemas.items()} if isinstance(c, Cassette) else c
    return {server: {t["name"]: normalize(t.get("inputSchema")) for t in tools} for server, tools in raw.items()}


def schema_unchanged(arg: Any, ctx: AssertionContext) -> Outcome:
    """Compare the live servers' tool schemas to the recorded ones (needs `cassette test --check-schemas`)."""
    if not arg:
        return OK
    if ctx.live_schemas is None:
        return Outcome(skipped="run with --check-schemas to compare against the live server")
    recorded, live = _schemas(ctx.baseline or ctx.cassette), _schemas(ctx.live_schemas)
    out = []
    for server in sorted(set(recorded) | set(live)):
        r, v = recorded.get(server, {}), live.get(server, {})
        for tool in sorted(set(r) | set(v)):
            if tool not in v:
                out.append(Failure(f"{server}.{tool} was removed from the server"))
            elif tool not in r:
                out.append(Failure(f"{server}.{tool} was added to the server"))
            elif r[tool] != v[tool]:
                out.append(Failure(f"{server}.{tool} input schema changed"))
    return _fail(*out)


def _load_function(ref: str, root: Path) -> Callable[[AssertionContext], Any]:
    """`path/to/file.py:func` (relative to the config) or `package.module:func`."""
    target, _, func = ref.rpartition(":")
    if not target or not func:
        raise ValueError(f"custom assertion must look like 'file.py:function', got {ref!r}")
    if target.endswith(".py"):
        path = (root / target).resolve()
        spec = importlib.util.spec_from_file_location(f"cassette_custom_{path.stem}", path)
        if spec is None or spec.loader is None:
            raise ValueError(f"cannot load {path}")
        mod = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = mod
        spec.loader.exec_module(mod)
    else:
        mod = importlib.import_module(target)
    fn: Callable[[AssertionContext], Any] = getattr(mod, func)
    return fn


def custom(arg: Any, ctx: AssertionContext) -> Outcome:
    """Your own function `(ctx) -> None | True | False | str | list[str]`; falsy-ok, a string or list is a failure."""
    out = []
    for ref in map(str, _as_list(arg)):
        res = _load_function(ref, ctx.root)(ctx)
        if res is None or res is True:
            continue
        if res is False:
            out.append(Failure(f"{ref} returned False"))
        else:
            out += [Failure(str(m)) for m in (res if isinstance(res, list) else [res])]
    return _fail(*out)


CHECKS: dict[str, Check] = {
    "forbid_tool": forbid_tool,
    "require_tool": require_tool,
    "tool_sequence": tool_sequence,
    "no_canary": no_canary,
    "links_allowlist": links_allowlist,
    "max_steps": max_steps,
    "max_cost_usd": max_cost_usd,
    "max_latency_ms": max_latency_ms,
    "output_matches": output_matches,
    "schema_unchanged": schema_unchanged,
    "custom": custom,
}
