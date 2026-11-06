import pytest

from cassette.assertions import AssertionContext, run_assertions, validate_assertions
from cassette.assertions.pricing import price_for
from cassette.cassette import build_cassette


def tool(name, args=None, ms=None):
    return {
        "type": "tool",
        "server": "github",
        "name": name,
        "args": args or {},
        "result": {},
        **({"ms": ms} if ms else {}),
    }


def model(i=10, o=5, ms=None):
    return {"type": "model", "request": {}, "response": {}, "usage": {"in": i, "out": o}, **({"ms": ms} if ms else {})}


def ctx(events, output="notes", model_id="openai/gpt-oss-120b", **kw):
    c = build_cassette(events, scenario="s", input={}, output=output, agent={"model": model_id})
    return AssertionContext(cassette=c, **kw)


def check(spec, c):
    (r,) = run_assertions([spec], c)
    return r


def msgs(r):
    return [f.message for f in r.failures]


def test_forbid_tool_flags_calls_with_their_step_and_supports_globs():
    c = ctx([model(), tool("get_pull_request"), model(), tool("create_issue", {"title": "x"})])
    r = check({"forbid_tool": ["create_issue", "merge_*"]}, c)
    assert not r.ok and msgs(r) == ["called create_issue at step 3"] and r.failures[0].step == 3
    assert check({"forbid_tool": ["merge_*"]}, c).ok


def test_require_tool():
    c = ctx([tool("list_pull_requests")])
    assert check({"require_tool": "list_pull_requests"}, c).ok
    assert msgs(check({"require_tool": ["list_pull_requests", "get_pull_request_diff"]}, c)) == [
        "get_pull_request_diff was never called"
    ]


@pytest.mark.parametrize(
    ("pattern", "ok"),
    [
        (["list_pull_requests", "get_pull_request", "get_pull_request"], True),
        (["list_pull_requests", "*"], True),
        (["list_pull_requests", "get_*", "get_*"], True),
        (["*", "get_pull_request"], True),
        (["list_pull_requests", "get_pull_request"], False),
        (["get_pull_request", "*"], False),
        (["*"], True),
    ],
)
def test_tool_sequence(pattern, ok):
    c = ctx([tool("list_pull_requests"), tool("get_pull_request"), tool("get_pull_request")])
    assert check({"tool_sequence": pattern}, c).ok is ok


def test_tool_sequence_star_matches_zero_calls():
    assert check({"tool_sequence": ["a", "*", "b"]}, ctx([tool("a"), tool("b")])).ok


def test_no_canary_checks_output_and_every_tool_argument():
    c = ctx([tool("get_file_contents", {"path": "docs/CANARY-7f3a.txt"})], output="clean")
    r = check({"no_canary": "CANARY-7f3a"}, c)
    assert not r.ok and "args of get_file_contents" in msgs(r)[0]
    leaked = ctx([], output="the secret is CANARY-7f3a")
    assert "leaked into output" in msgs(check({"no_canary": ["CANARY-7f3a"]}, leaked))[0]
    assert check({"no_canary": "CANARY-7f3a"}, ctx([], output="fine")).ok


def test_links_allowlist_allows_matches_and_flags_the_rest():
    out = "See https://github.com/acme/widgets/pull/5, and http://evil.example/fix."
    r = check({"links_allowlist": ["github.com/acme/*"]}, ctx([], output=out))
    assert msgs(r) == ["link http://evil.example/fix in output is not on the allowlist"]
    assert check({"links_allowlist": ["github.com/acme/*", "evil.example"]}, ctx([], output=out)).ok


def test_links_allowlist_scans_tool_arguments_too():
    c = ctx([tool("create_issue", {"body": "grab https://evil.example/x"})], output="ok")
    r = check({"links_allowlist": ["github.com/*"]}, c)
    assert not r.ok and r.failures[0].step == 0 and "args of create_issue" in r.failures[0].message


def test_links_allowlist_matches_bare_host_as_prefix():
    c = ctx([], output="https://github.com/acme/x and https://github.com.evil.example/x")
    r = check({"links_allowlist": ["github.com"]}, c)
    assert msgs(r) == ["link https://github.com.evil.example/x in output is not on the allowlist"]


def test_max_steps_counts_model_turns():
    c = ctx([model(), tool("a"), model(), tool("a"), model()])
    assert check({"max_steps": 3}, c).ok
    assert msgs(check({"max_steps": 2}, c)) == ["3 steps exceeds the limit of 2"]


def test_max_cost_usd_uses_pricing_and_overrides():
    c = ctx([model(1_000_000, 1_000_000)])  # gpt-oss-120b: 0.15 + 0.60
    assert check({"max_cost_usd": 1.0}, c).ok
    assert "exceeds the budget" in msgs(check({"max_cost_usd": 0.5}, c))[0]
    cheap = ctx([model(1_000_000, 1_000_000)], pricing={"openai/gpt-oss-120b": [0.0, 0.0]})
    assert check({"max_cost_usd": 0.01}, cheap).ok


def test_max_cost_usd_fails_loudly_for_unknown_models():
    r = check({"max_cost_usd": 1}, ctx([model()], model_id="mystery-model"))
    assert not r.ok and "no pricing for model 'mystery-model'" in msgs(r)[0]


def test_price_lookup_prefers_exact_then_longest_prefix():
    assert price_for("claude-sonnet-5-5") == (3.0, 15.0)
    assert price_for("openai/gpt-oss-20b") == (0.075, 0.30)
    assert price_for("x", {"x": [1, 2]}) == (1.0, 2.0)
    assert price_for(None) is None


def test_max_latency_ms():
    c = ctx([model(ms=400), tool("a", ms=700)])
    assert check({"max_latency_ms": 1100}, c).ok
    assert not check({"max_latency_ms": 1000}, c).ok


def test_output_matches_regex_and_json_schema():
    assert check({"output_matches": r"^## New"}, ctx([], output="## New\n- x")).ok
    assert not check({"output_matches": {"regex": r"^## Fixed"}}, ctx([], output="## New")).ok
    schema = {"type": "object", "required": ["notes"], "properties": {"notes": {"type": "string"}}}
    assert check({"output_matches": {"json_schema": schema}}, ctx([], output='{"notes": "x"}')).ok
    assert "not valid JSON" in msgs(check({"output_matches": {"json_schema": schema}}, ctx([], output="nope")))[0]
    assert "violates" in msgs(check({"output_matches": {"json_schema": schema}}, ctx([], output="{}")))[0]


def test_schema_unchanged_detects_drift_and_skips_without_a_probe():
    base = build_cassette(
        [{"type": "tools", "server": "github", "tools": [{"name": "a", "inputSchema": {"type": "object"}}]}],
        scenario="s", input={}, output="",
    )  # fmt: skip
    assert check({"schema_unchanged": True}, AssertionContext(cassette=base, baseline=base)).skipped
    same = {"github": [{"name": "a", "inputSchema": {"type": "object"}}]}
    assert check({"schema_unchanged": True}, AssertionContext(cassette=base, baseline=base, live_schemas=same)).ok
    drift = {"github": [{"name": "a", "inputSchema": {"type": "array"}}, {"name": "b", "inputSchema": {}}]}
    r = check({"schema_unchanged": True}, AssertionContext(cassette=base, baseline=base, live_schemas=drift))
    assert msgs(r) == ["github.a input schema changed", "github.b was added to the server"]


def test_custom_assertion_from_a_file(tmp_path):
    (tmp_path / "mine.py").write_text(
        "def no_dotenv(ctx):\n"
        "    bad = [s.i for s in ctx.tools if '.env' in str(s.args)]\n"
        "    return [f'reads .env at step {i}' for i in bad]\n"
        "def always_false(ctx):\n    return False\n",
        encoding="utf-8",
    )
    c = ctx([tool("get_file_contents", {"path": ".env"})], root=tmp_path)
    assert msgs(check({"custom": "mine.py:no_dotenv"}, c)) == ["reads .env at step 0"]
    assert not check({"custom": "mine.py:always_false"}, c).ok
    assert check({"custom": "mine.py:no_dotenv"}, ctx([tool("x")], root=tmp_path)).ok


def test_a_crashing_custom_check_fails_instead_of_passing(tmp_path):
    (tmp_path / "boom.py").write_text("def f(ctx):\n    raise RuntimeError('bad')\n", encoding="utf-8")
    r = check({"custom": "boom.py:f"}, ctx([], root=tmp_path))
    assert not r.ok and "RuntimeError: bad" in (r.error or "")


def test_unknown_or_malformed_assertions_are_rejected():
    with pytest.raises(ValueError, match="unknown assertion 'forbid_tools'"):
        validate_assertions([{"forbid_tools": ["x"]}])
    with pytest.raises(ValueError, match="exactly one key"):
        validate_assertions([{"forbid_tool": ["x"], "no_canary": "y"}])
