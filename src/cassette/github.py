"""Post (or update) the Cassette PR comment through the GitHub REST API. Stdlib only, so the Action needs no extras."""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from collections.abc import Callable
from pathlib import Path
from typing import Any

from .report.markdown import MARKER

API = "https://api.github.com"


class GitHubError(Exception):
    def __init__(self, status: int, message: str) -> None:
        super().__init__(f"GitHub API {status}: {message}")
        self.status = status


Request = Callable[[str, str, dict[str, Any] | None], Any]


def _request_factory(token: str) -> Request:
    def request(method: str, url: str, body: dict[str, Any] | None = None) -> Any:
        req = urllib.request.Request(  # noqa: S310 - https GitHub API (or a local test server)
            url,
            method=method,
            data=json.dumps(body).encode() if body is not None else None,
            headers={
                "Authorization": f"Bearer {token}",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
                "User-Agent": "cassette-cli",
                "Content-Type": "application/json",
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:  # noqa: S310
                raw = resp.read()
                return json.loads(raw) if raw else None
        except urllib.error.HTTPError as e:
            try:
                msg = json.loads(e.read()).get("message", e.reason)
            except (ValueError, AttributeError):
                msg = str(e.reason)
            raise GitHubError(e.code, str(msg)) from None

    return request


def find_comment(request: Request, api: str, repo: str, pr: int) -> dict[str, Any] | None:
    """The existing Cassette comment on the PR, identified by its hidden marker (not by author)."""
    page = 1
    while True:
        batch = request("GET", f"{api}/repos/{repo}/issues/{pr}/comments?per_page=100&page={page}", None)
        for c in batch:
            if MARKER in (c.get("body") or ""):
                return dict(c)
        if len(batch) < 100:
            return None
        page += 1


def upsert_comment(
    repo: str, pr: int, body: str, token: str, *, api: str = API, request: Request | None = None
) -> tuple[str, str]:
    """Update the PR's Cassette comment if there is one, otherwise create it. Returns (action, html_url)."""
    req = request or _request_factory(token)
    existing = find_comment(req, api, repo, pr)
    if existing:
        done = req("PATCH", f"{api}/repos/{repo}/issues/comments/{existing['id']}", {"body": body})
        return "updated", str(done.get("html_url", ""))
    done = req("POST", f"{api}/repos/{repo}/issues/{pr}/comments", {"body": body})
    return "created", str(done.get("html_url", ""))


def pr_number_from_event(env: dict[str, str] | None = None) -> int | None:
    """The PR number from the Actions event payload, if this run is for a pull request."""
    e = env if env is not None else dict(os.environ)
    path = e.get("GITHUB_EVENT_PATH")
    if not path or not Path(path).is_file():
        return None
    event = json.loads(Path(path).read_text(encoding="utf-8"))
    number = (event.get("pull_request") or {}).get("number") or event.get("number")
    return int(number) if number else None
