import json
import subprocess
import sys
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any

import pytest

from cassette.github import find_comment, pr_number_from_event, upsert_comment
from cassette.report import MARKER


def test_find_comment_matches_the_marker_not_the_author_and_pages():
    pages = {1: [{"id": i, "body": "other"} for i in range(100)], 2: [{"id": 500, "body": f"{MARKER}\nhi"}]}
    calls: list[str] = []

    def req(method: str, url: str, body: Any) -> Any:
        calls.append(url)
        return pages[int(url.rsplit("page=", 1)[1])]

    assert find_comment(req, "https://x", "o/r", 7) == {"id": 500, "body": f"{MARKER}\nhi"}
    assert len(calls) == 2


def test_upsert_creates_then_updates():
    store: list[dict[str, Any]] = []

    def req(method: str, url: str, body: Any) -> Any:
        if method == "GET":
            return list(store)
        if method == "POST":
            store.append({"id": 1, "body": body["body"], "html_url": "u1"})
            return store[0]
        store[0]["body"] = body["body"]
        return store[0]

    assert upsert_comment("o/r", 3, f"{MARKER} v1", "t", api="https://x", request=req) == ("created", "u1")
    assert upsert_comment("o/r", 3, f"{MARKER} v2", "t", api="https://x", request=req) == ("updated", "u1")
    assert len(store) == 1 and store[0]["body"].endswith("v2")


def test_pr_number_from_the_event_payload(tmp_path):
    ev = tmp_path / "event.json"
    ev.write_text(json.dumps({"pull_request": {"number": 42}}), encoding="utf-8")
    assert pr_number_from_event({"GITHUB_EVENT_PATH": str(ev)}) == 42
    assert pr_number_from_event({}) is None
    ev.write_text(json.dumps({"ref": "refs/heads/main"}), encoding="utf-8")
    assert pr_number_from_event({"GITHUB_EVENT_PATH": str(ev)}) is None


class FakeGitHub:
    """A local stand-in for the GitHub issues-comments API."""

    def __init__(self, fail_with: int | None = None) -> None:
        self.comments: list[dict[str, Any]] = []
        self.requests: list[tuple[str, str]] = []
        self.auth: set[str] = set()
        outer = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *a: Any) -> None:  # keep test output quiet
                pass

            def _send(self, status: int, payload: Any) -> None:
                data = json.dumps(payload).encode()
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def _handle(self, method: str) -> None:
                outer.requests.append((method, self.path))
                outer.auth.add(self.headers.get("Authorization", ""))
                if fail_with:
                    return self._send(fail_with, {"message": "Resource not accessible by integration"})
                body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))) or "null")
                if method == "GET":
                    return self._send(200, outer.comments)
                if method == "POST":
                    c = {"id": len(outer.comments) + 1, "body": body["body"], "html_url": "http://gh/c/1"}
                    outer.comments.append(c)
                    return self._send(201, c)
                outer.comments[0]["body"] = body["body"]
                return self._send(200, outer.comments[0])

            def do_GET(self) -> None:
                self._handle("GET")

            def do_POST(self) -> None:
                self._handle("POST")

            def do_PATCH(self) -> None:
                self._handle("PATCH")

        self.server = HTTPServer(("127.0.0.1", 0), Handler)
        self.url = f"http://127.0.0.1:{self.server.server_port}"
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def close(self) -> None:
        self.server.shutdown()


@pytest.fixture
def report_dir(tmp_path):
    d = tmp_path / "cassette-report"
    d.mkdir()
    report = {
        "passed": False,
        "summary": {
            "scenarios": 1, "failed": 1, "changed": 1, "attacksCaught": 0,
            "tokensBase": 100, "tokensNew": 108, "tokensDeltaPct": 8,
        },
        "scenarios": [],
    }  # fmt: skip
    (d / "results.json").write_text(json.dumps(report), encoding="utf-8")
    return d


def run_comment(report_dir, api_url, *extra, token="tok"):
    import os

    env = {**os.environ, "GITHUB_TOKEN": token, "GITHUB_REPOSITORY": "o/r"}
    return subprocess.run(
        [sys.executable, "-m", "cassette", "comment", "--report-dir", str(report_dir), "--pr", "9",
         "--api-url", api_url, *extra],
        capture_output=True, text=True, encoding="utf-8", env=env, timeout=60,
    )  # fmt: skip


def test_cli_comment_creates_then_updates_one_comment(report_dir):
    gh = FakeGitHub()
    try:
        r1 = run_comment(report_dir, gh.url, "--url", "https://example.test/artifact")
        assert r1.returncode == 0, r1.stderr
        assert "comment created" in r1.stdout
        r2 = run_comment(report_dir, gh.url)
        assert "comment updated" in r2.stdout
        assert len(gh.comments) == 1
        assert gh.comments[0]["body"].startswith(MARKER) and "1 changed, +8% tokens" in gh.comments[0]["body"]
        assert gh.auth == {"Bearer tok"}
    finally:
        gh.close()


def test_cli_comment_treats_a_read_only_token_as_a_warning_exit_3(report_dir):
    gh = FakeGitHub(fail_with=403)
    try:
        r = run_comment(report_dir, gh.url)
        assert r.returncode == 3
        assert "could not post the PR comment" in r.stderr and "forks" in r.stderr
    finally:
        gh.close()


def test_cli_comment_without_credentials_explains_what_is_missing(report_dir, monkeypatch):
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    r = subprocess.run(
        [sys.executable, "-m", "cassette", "comment", "--report-dir", str(report_dir)],
        capture_output=True, text=True, encoding="utf-8", timeout=60,
        env={k: v for k, v in __import__("os").environ.items() if not k.startswith("GITHUB_")},
    )  # fmt: skip
    assert r.returncode != 0 and "need --repo, --pr and $GITHUB_TOKEN" in r.stderr
