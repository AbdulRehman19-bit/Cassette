"""Week 1 gate: replaying a recorded run makes zero live tool calls and reaches the same output."""

import json
import subprocess
import sys
from pathlib import Path

import pytest

from cassette.cassette import read_scenario
from cassette.config import Config, load_config
from cassette.runner import run_scenario

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture(scope="module")
def project(tmp_path_factory: pytest.TempPathFactory) -> tuple[Path, Path]:
    d = tmp_path_factory.mktemp("e2e")
    counter = d / "live-calls.txt"
    cfg = d / "cassette.yaml"
    agent_cmd = f"{sys.executable} {FIXTURES / 'fake_agent.py'}"
    cfg.write_text(
        "\n".join(
            [
                "agent:",
                f"  command: {json.dumps(agent_cmd)}",
                "servers:",
                "  fake:",
                f"    command: {json.dumps(sys.executable)}",
                f"    args: [{json.dumps(str(FIXTURES / 'fake_server.py'))}]",
                f"    env: {{ LIVE_COUNT_FILE: {json.dumps(str(counter))} }}",
                "scenarios:",
                "  - name: basic",
                "    input: { repo: acme/widgets }",
            ]
        ),
        encoding="utf-8",
    )
    return cfg, counter


def live_calls(counter: Path) -> int:
    return len(counter.read_text().split()) if counter.exists() else 0


def cli(cfg: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "cassette", *args, "-c", str(cfg)],
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=60,
    )


@pytest.fixture(scope="module")
def cfg_obj(project: tuple[Path, Path]) -> Config:
    return load_config(project[0])


@pytest.mark.asyncio(loop_scope="module")
async def test_records_a_run_into_a_cassette(project, cfg_obj):
    _, counter = project
    run = await run_scenario(cfg_obj, "basic", mode="record", quiet=True)
    assert run.exit_code == 0, run.stderr
    assert run.written is not None
    c = read_scenario(cfg_obj.cassettes_path, "basic")
    assert [s.type for s in c.steps] == ["model", "tool", "model", "tool", "model"]
    assert c.output == "## New\n- Dark mode"
    assert list(c.toolSchemas) == ["fake"]
    assert live_calls(counter) == 2


@pytest.mark.asyncio(loop_scope="module")
async def test_replay_makes_zero_live_tool_calls_and_same_output(project, cfg_obj):
    _, counter = project
    before = live_calls(counter)
    run = await run_scenario(cfg_obj, "basic", mode="replay", quiet=True)
    assert run.exit_code == 0, run.stderr
    assert run.divergences == []
    assert run.cassette.output == "## New\n- Dark mode"
    assert live_calls(counter) == before


@pytest.mark.asyncio(loop_scope="module")
async def test_replaying_twice_gives_the_same_result(cfg_obj):
    a = await run_scenario(cfg_obj, "basic", mode="replay", quiet=True)
    b = await run_scenario(cfg_obj, "basic", mode="replay", quiet=True)
    key = lambda r: [(s.name, s.args, s.result) for s in r.cassette.tool_steps()]  # noqa: E731
    assert key(a) == key(b)


def test_cli_offline_test_passes_and_reports_identical_output(project):
    cfg, counter = project
    before = live_calls(counter)
    r = cli(cfg, "test", "--offline")
    assert r.returncode == 0, r.stdout + r.stderr
    assert "output identical" in r.stdout
    assert live_calls(counter) == before


def test_unrecorded_call_is_a_divergence_and_exits_1(project, cfg_obj):
    cfg, _ = project
    path = cfg_obj.cassettes_path / "basic.cassette.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    data["steps"] = [s for s in data["steps"] if s.get("name") != "get_pull_request"]
    path.write_text(json.dumps(data), encoding="utf-8")
    r = cli(cfg, "test")
    assert r.returncode == 1, r.stdout + r.stderr
    assert "no recorded result for get_pull_request" in r.stdout
