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
                "assertions:",
                "  - forbid_tool: [get_file_contents, create_issue]",
                "  - require_tool: list_pull_requests",
                "  - max_steps: 5",
                "  - no_canary: CANARY-7f3a",
                '  - links_allowlist: ["github.com/acme/*"]',
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
        cwd=cfg.parent,  # reports land beside the test config, not in the repo
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


def test_model_swap_changes_tool_calls_while_output_looks_fine(project):
    """The headline: the final text is unchanged, but the agent now calls a different tool."""
    cfg, counter = project
    before = live_calls(counter)
    r = cli(cfg, "test", "--model", "small")
    assert r.returncode == 1, r.stdout + r.stderr
    assert "trajectory changed" in r.stdout
    assert "- step 3  get_pull_request(number: 7)" in r.stdout
    assert '+ step 3  get_file_contents(path: "CHANGELOG.md")' in r.stdout
    assert "output similarity 1.00 (looks fine; behavior changed)" in r.stdout
    assert live_calls(counter) == before  # still zero live tool calls


def test_assertions_pass_on_a_healthy_run_and_are_listed_in_json(project):
    cfg, _ = project
    r = cli(cfg, "test", "--offline", "--json")
    assert r.returncode == 0, r.stdout + r.stderr
    (s,) = json.loads(r.stdout)["scenarios"]
    assert [a["name"] for a in s["assertions"]] == [
        "forbid_tool",
        "require_tool",
        "max_steps",
        "no_canary",
        "links_allowlist",
    ]
    assert all(a["ok"] for a in s["assertions"])


def test_forbid_tool_assertion_fails_the_run_when_the_model_swap_calls_a_forbidden_tool(project):
    cfg, _ = project
    r = cli(cfg, "test", "--model", "small")
    assert r.returncode == 1, r.stdout + r.stderr
    assert "forbid_tool: called get_file_contents at step 3" in r.stdout


def test_a_misspelled_assertion_stops_the_run_instead_of_passing_silently(project, tmp_path):
    cfg, _ = project
    bad = tmp_path / "bad.yaml"
    bad.write_text(cfg.read_text(encoding="utf-8") + "\n  - forbid_tools: [x]\n", encoding="utf-8")
    r = cli(bad, "test", "--offline")
    assert r.returncode != 0
    assert "unknown assertion 'forbid_tools'" in r.stdout + r.stderr


def test_a_failing_run_writes_json_html_and_pr_comment(project):
    cfg, _ = project
    r = cli(cfg, "test", "--model", "small")
    assert r.returncode == 1
    report = cfg.parent / "cassette-report"
    data = json.loads((report / "results.json").read_text(encoding="utf-8"))
    assert data["passed"] is False and data["summary"]["changed"] == 1
    html = (report / "index.html").read_text(encoding="utf-8")
    assert "<script" not in html and "http://" not in html.replace(
        "http://www.w3.org", ""
    )  # self-contained, no network
    assert "get_file_contents" in html and "behavior changed" in html and "FAIL" in html
    comment = (report / "comment.md").read_text(encoding="utf-8")
    assert comment.startswith("<!-- cassette-report -->")
    assert "### ❌ Cassette: 1 changed" in comment
    assert "- step 3  get_pull_request(number: 7)" in comment
    assert '+ step 3  get_file_contents(path: "CHANGELOG.md")' in comment
    assert "forbid_tool" in comment


def test_report_command_rebuilds_files_and_adds_the_link(project):
    cfg, _ = project
    cli(cfg, "test", "--model", "small")
    report = cfg.parent / "cassette-report"
    (report / "comment.md").unlink()
    (report / "index.html").unlink()
    r = subprocess.run(
        [sys.executable, "-m", "cassette", "report", "--url", "https://example.test/run/1"],
        capture_output=True, text=True, encoding="utf-8", cwd=cfg.parent,
    )  # fmt: skip
    assert r.returncode == 0, r.stderr
    assert "[Open the full report](https://example.test/run/1)" in (report / "comment.md").read_text(encoding="utf-8")
    assert (report / "index.html").exists()


def test_report_command_without_a_prior_run_explains_itself(tmp_path):
    r = subprocess.run(
        [sys.executable, "-m", "cassette", "report"], capture_output=True, text=True, encoding="utf-8", cwd=tmp_path
    )
    assert r.returncode != 0 and "run `cassette test` first" in r.stderr


def test_update_refuses_a_run_with_unrecorded_calls_then_accepts_a_clean_one(project, cfg_obj):
    cfg, _ = project
    base_file = cfg_obj.cassettes_path / "basic.cassette.json"
    before = base_file.read_bytes()
    cli(cfg, "test", "--model", "small")  # the swapped model calls get_file_contents: no recorded answer
    r = cli(cfg, "update")
    assert "had no answer for" in r.stdout and base_file.read_bytes() == before

    cli(cfg, "test", "--offline")  # a clean run
    r = cli(cfg, "update")
    assert "baseline updated" in r.stdout and "1 baseline(s) updated" in r.stdout
    assert cli(cfg, "test", "--offline").returncode == 0


def test_json_output_is_machine_readable(project):
    cfg, _ = project
    r = cli(cfg, "test", "--model", "small", "--json")
    data = json.loads(r.stdout)
    assert data["passed"] is False
    (s,) = data["scenarios"]
    assert s["name"] == "basic" and s["counts"]["tool_removed"] == 1 and s["counts"]["tool_added"] == 1


def test_cassette_diff_command_compares_two_files(project, cfg_obj):
    cfg, _ = project
    a = cfg_obj.cassettes_path / "basic.cassette.json"
    data = json.loads(a.read_text(encoding="utf-8"))
    data["steps"] = [s for s in data["steps"] if s.get("name") != "get_pull_request"]
    b = a.with_name("other.cassette.json")
    b.write_text(json.dumps(data), encoding="utf-8")
    r = subprocess.run(
        [sys.executable, "-m", "cassette", "diff", str(a), str(b)], capture_output=True, text=True, encoding="utf-8"
    )
    assert r.returncode == 0, r.stderr
    assert "- step 3  get_pull_request(number: 7)" in r.stdout
    b.unlink()


def test_unrecorded_call_is_a_divergence_and_exits_1(project, cfg_obj):
    cfg, _ = project
    path = cfg_obj.cassettes_path / "basic.cassette.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    data["steps"] = [s for s in data["steps"] if s.get("name") != "get_pull_request"]
    path.write_text(json.dumps(data), encoding="utf-8")
    r = cli(cfg, "test")
    assert r.returncode == 1, r.stdout + r.stderr
    assert "no recorded result for get_pull_request" in r.stdout
