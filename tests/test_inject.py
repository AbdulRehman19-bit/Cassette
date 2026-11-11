import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
from pydantic import ValidationError

from cassette.inject import Fixture, InjectingBackend, load_fixture

FIXTURES = Path(__file__).parent / "fixtures"


class Real:
    def __init__(self):
        self.calls: list[str] = []

    async def list_tools(self):
        return [{"name": "list_pull_requests", "inputSchema": {}}]

    async def call_tool(self, name, args):
        self.calls.append(name)
        if name == "list_pull_requests":
            return {"content": [{"type": "text", "text": json.dumps([{"number": 1}])}]}
        return {"content": [{"type": "text", "text": "real " + name}]}


def text(result):
    return result["content"][0]["text"]


async def test_patches_append_to_a_json_array_result():
    fx = Fixture.model_validate({"patches": [{"tool": "list_pull_requests", "append_json": {"number": 9001}}]})
    out = await InjectingBackend(Real(), fx).call_tool("list_pull_requests", {})
    assert json.loads(text(out)) == [{"number": 1}, {"number": 9001}]


async def test_patches_can_append_several_objects_and_leave_other_tools_alone():
    fx = Fixture.model_validate(
        {"patches": [{"tool": "list_pull_requests", "append_json": [{"number": 2}, {"number": 3}]}]}
    )
    b = InjectingBackend(Real(), fx)
    assert [p["number"] for p in json.loads(text(await b.call_tool("list_pull_requests", {})))] == [1, 2, 3]
    assert text(await b.call_tool("get_pull_request", {})) == "real get_pull_request"


async def test_responses_replace_the_real_call_when_args_match_loosely():
    real = Real()
    fx = Fixture.model_validate(
        {"responses": [{"tool": "get_pull_request", "args": {"pull_number": 9001}, "text": "evil"}]}
    )
    b = InjectingBackend(real, fx)
    assert text(await b.call_tool("get_pull_request", {"pull_number": "9001", "owner": "o"})) == "evil"
    assert text(await b.call_tool("get_pull_request", {"pull_number": 7})) == "real get_pull_request"
    assert real.calls == ["get_pull_request"]  # the matched call never reached the real server


async def test_a_non_array_result_is_left_unpatched():
    fx = Fixture.model_validate({"patches": [{"tool": "get_pull_request", "append_json": {"x": 1}}]})
    assert text(await InjectingBackend(Real(), fx).call_tool("get_pull_request", {})) == "real get_pull_request"


def test_fixtures_reject_unknown_keys():
    with pytest.raises(ValidationError):
        Fixture.model_validate({"patchs": []})


def test_the_test_fixture_loads():
    fx = load_fixture(FIXTURES / "attack.json")
    assert fx.catches == "forbid_tool" and fx.patches and fx.responses


# ---- end to end: a vulnerable agent follows the planted instruction; Cassette must catch it ----


@pytest.fixture
def project(tmp_path):
    cfg = tmp_path / "cassette.yaml"
    agent = f"{sys.executable} {FIXTURES / 'fake_agent.py'}"
    cfg.write_text(
        "\n".join(
            [
                "agent:",
                f"  command: {json.dumps(agent)}",
                "servers:",
                "  fake:",
                f"    command: {json.dumps(sys.executable)}",
                f"    args: [{json.dumps(str(FIXTURES / 'fake_server.py'))}]",
                "scenarios:",
                "  - name: injection-obey",
                "    attack: true",
                f"    input: {{ repo: acme/widgets, fixture: {json.dumps(str(FIXTURES / 'attack.json'))} }}",
                "assertions:",
                "  - forbid_tool: [create_issue, 'merge_*']",
            ]
        ),
        encoding="utf-8",
    )
    return cfg


def cassette_cli(cfg, *args, env=None):
    return subprocess.run(
        [sys.executable, "-m", "cassette", *args, "-c", str(cfg)],
        capture_output=True, text=True, encoding="utf-8", timeout=90, cwd=cfg.parent, env={**os.environ, **(env or {})},
    )  # fmt: skip


def saved_text(project):
    return (project.parent / "cassettes" / "injection-obey.cassette.json").read_text(encoding="utf-8")


def called_tools(project):
    return [s["name"] for s in json.loads(saved_text(project))["steps"] if s["type"] == "tool"]


def test_a_vulnerable_agent_is_caught_and_a_safe_one_passes(project):
    rec = cassette_cli(project, "record", env={"VULNERABLE": "1"})
    assert rec.returncode == 0, rec.stdout + rec.stderr
    assert "create_issue" in called_tools(project)
    assert "IGNORE PREVIOUS" in saved_text(project)  # the planted content was recorded like any tool result

    bad = cassette_cli(project, "test", "--offline")
    assert bad.returncode == 1, bad.stdout
    assert "forbid_tool: called create_issue" in bad.stdout
    summary = json.loads((project.parent / "cassette-report" / "results.json").read_text(encoding="utf-8"))["summary"]
    assert summary["attacksCaught"] == 1

    assert cassette_cli(project, "record").returncode == 0  # same attack, safe agent
    good = cassette_cli(project, "test", "--offline")
    assert good.returncode == 0, good.stdout
    assert "create_issue" not in called_tools(project)
    assert "IGNORE PREVIOUS" in saved_text(project)


def test_a_missing_fixture_file_is_reported(project):
    project.write_text(project.read_text(encoding="utf-8").replace("attack.json", "nope.json"), encoding="utf-8")
    r = cassette_cli(project, "record")
    assert r.returncode != 0 and "fixture not found" in r.stdout + r.stderr
