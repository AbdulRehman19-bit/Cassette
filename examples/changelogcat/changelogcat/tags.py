"""Pick the tag a release should be compared against. `python -m changelogcat.tags previous --repo o/r --tag v1.4.0`."""

from __future__ import annotations

import argparse
import os
import re
import sys
from typing import Any

import httpx


def version_key(tag: str) -> tuple[Any, ...]:
    """`v1.10.0` > `v1.9.0`; pre-releases (`1.0.0-rc1`) sort before the final release."""
    m = re.match(r"^[vV]?(\d+(?:\.\d+)*)(.*)$", tag)
    if not m:
        return ((), 0, tag)
    nums = tuple(int(x) for x in m.group(1).split("."))
    return (nums, 0 if m.group(2) else 1, m.group(2))


def previous_tag(tags: list[str], current: str) -> str | None:
    """The highest version that is lower than `current`, ignoring tags that don't look like versions."""
    cur = version_key(current)
    older = [t for t in tags if version_key(t)[0] and version_key(t) < cur]
    return max(older, key=version_key) if older else None


def fetch_tags(repo: str, token: str = "", *, client: httpx.Client | None = None) -> list[str]:
    headers = {"Accept": "application/vnd.github+json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    http = client or httpx.Client(base_url="https://api.github.com", headers=headers, timeout=30)
    tags: list[str] = []
    for page in range(1, 11):
        res = http.get(f"/repos/{repo}/tags", params={"per_page": 100, "page": page})
        res.raise_for_status()
        batch = res.json()
        tags += [t["name"] for t in batch]
        if len(batch) < 100:
            break
    return tags


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="changelogcat.tags")
    ap.add_argument("command", choices=["previous"])
    ap.add_argument("--repo", required=True)
    ap.add_argument("--tag", required=True)
    args = ap.parse_args(argv)
    prev = previous_tag(fetch_tags(args.repo, os.environ.get("GITHUB_TOKEN", "")), args.tag)
    if prev is None:
        print(f"no earlier tag than {args.tag} in {args.repo}", file=sys.stderr)
        return 1
    print(prev)
    return 0


if __name__ == "__main__":
    sys.exit(main())
