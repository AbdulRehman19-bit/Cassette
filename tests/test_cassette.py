import pytest
from pydantic import ValidationError

from cassette.cassette import (
    Cassette,
    build_cassette,
    canonical_args,
    list_cassettes,
    normalize,
    read_scenario,
    write_cassette,
)
from cassette.config import expand_env, parse_config


def sample(**over):
    events = [
        {"type": "tools", "server": "github", "tools": [{"name": "list_pull_requests", "inputSchema": {}}]},
        {"type": "model", "request": {"id": "msg_01ABCdef123456"}, "response": {"at": "2026-11-05T10:00:01Z"}},
        {
            "type": "tool",
            "server": "github",
            "name": "list_pull_requests",
            "args": {"b": 1, "a": 2},
            "result": {"ok": True},
        },
    ]
    kw = {
        "scenario": "release-v1.4",
        "input": {"repo": "acme/widgets"},
        "output": "## New",
        "recorded_at": "2026-11-05T10:00:00.000Z",
        **over,
    }
    return build_cassette(events, **kw)


def test_normalize_replaces_volatile_values_and_sorts_keys():
    out = normalize(
        {"z": "at 2026-01-02T03:04:05Z", "a": "9b2e7c1a-1111-4222-8333-444455556666", "m": "toolu_01AbCdEfGh"}
    )
    assert list(out) == ["a", "m", "z"]
    assert out == {"a": "<id>", "m": "<id>", "z": "at <timestamp>"}


def test_arg_key_order_is_irrelevant():
    assert canonical_args({"a": 1, "b": 2}) == canonical_args({"b": 2, "a": 1})


def test_build_orders_steps_and_captures_schemas():
    c = sample()
    assert [s.type for s in c.steps] == ["model", "tool"]
    assert [s.i for s in c.steps] == [0, 1]
    assert c.toolSchemas["github"][0].name == "list_pull_requests"


def test_round_trip_normalizes_on_write(tmp_path):
    path = write_cassette(tmp_path, sample())
    raw = path.read_text(encoding="utf-8")
    assert "2026-11-05" not in raw and "msg_01ABC" not in raw
    back = read_scenario(tmp_path, "release-v1.4")
    assert back.recordedAt == "<normalized>"
    assert len(back.steps) == 2


def test_runs_differing_only_in_volatile_fields_write_identical_bytes(tmp_path):
    p = write_cassette(tmp_path, sample())
    first = p.read_bytes()
    write_cassette(tmp_path, sample(recorded_at="2030-01-01T00:00:00Z"))
    assert p.read_bytes() == first


def test_optional_fields_stay_absent_not_null(tmp_path):
    raw = write_cassette(tmp_path, sample()).read_text(encoding="utf-8")
    assert '"ms"' not in raw and '"isError"' not in raw


def test_list_cassettes_tolerates_missing_dir(tmp_path):
    write_cassette(tmp_path, sample())
    assert list_cassettes(tmp_path) == ["release-v1.4"]
    assert list_cassettes(tmp_path / "nope") == []


def test_invalid_cassettes_are_rejected():
    with pytest.raises(ValidationError):
        Cassette.model_validate({"scenario": "x", "recordedAt": "t", "steps": [{"i": 0, "type": "tool"}]})


def test_config_parsing_and_command_split(tmp_path):
    cfg = parse_config(
        """
agent: {command: "node agent.js"}
servers:
  github: {command: "npx -y @modelcontextprotocol/server-github"}
scenarios:
  - {name: release-v1.4, input: {repo: acme/widgets}}
diff: {ignoreArgs: [per_page]}
""",
        tmp_path / "cassette.yaml",
    )
    assert cfg.servers["github"].split() == ("npx", ["-y", "@modelcontextprotocol/server-github"])
    assert cfg.diff.failOn == ["tool_added", "tool_removed", "tool_args_changed"]
    assert cfg.cassettes_path == (tmp_path / "cassettes").resolve()


def test_config_rejects_bad_scenario_names_and_typos(tmp_path):
    with pytest.raises(ValidationError):
        parse_config("agent: {command: x}\nservers: {}\nscenarios: [{name: 'a b'}]", tmp_path / "c.yaml")
    with pytest.raises(ValidationError):
        parse_config("agent: {command: x}\nservers: {}\nscenarioz: []", tmp_path / "c.yaml")


def test_expand_env():
    assert expand_env("tok-${A}-${MISSING}", {"A": "1"}) == "tok-1-"
