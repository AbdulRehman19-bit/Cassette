import json
import subprocess
import sys
from pathlib import Path

import pytest

FIXTURES = Path(__file__).parent / "fixtures"
NAMES = ["one", "two", "three"]


@pytest.fixture(scope="module")
def project(tmp_path_factory: pytest.TempPathFactory) -> Path:
    d = tmp_path_factory.mktemp("jobs")
    cfg = d / "cassette.yaml"
    agent = f"{sys.executable} {FIXTURES / 'fake_agent.py'}"
    lines = [
        "agent:",
        f"  command: {json.dumps(agent)}",
        "servers:",
        "  fake:",
        f"    command: {json.dumps(sys.executable)}",
        f"    args: [{json.dumps(str(FIXTURES / 'fake_server.py'))}]",
        "scenarios:",
        *[f"  - name: {n}\n    input: {{ repo: acme/widgets }}" for n in NAMES],
        "assertions:",
        "  - require_tool: list_pull_requests",
    ]
    cfg.write_text("\n".join(lines), encoding="utf-8")
    assert cli(cfg, "record").returncode == 0
    return cfg


def cli(cfg: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "cassette", *args, "-c", str(cfg)],
        capture_output=True, text=True, encoding="utf-8", timeout=120, cwd=cfg.parent,
    )  # fmt: skip


def names_in_order(stdout: str) -> list[str]:
    return [ln.split()[1] for ln in stdout.splitlines() if ln[:1] in "✓×"]


def test_parallel_run_prints_in_config_order_and_matches_a_sequential_run(project):
    par = cli(project, "test", "--offline", "--jobs", "3")
    seq = cli(project, "test", "--offline", "--jobs", "1")
    assert par.returncode == 0 and seq.returncode == 0, par.stdout + par.stderr + seq.stdout + seq.stderr
    assert names_in_order(par.stdout) == NAMES == names_in_order(seq.stdout)


def test_jobs_must_be_positive(project):
    r = cli(project, "test", "--offline", "--jobs", "0")
    assert r.returncode != 0 and "--jobs" in r.stderr
