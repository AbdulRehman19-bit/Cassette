import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from changelogcat.compact import MAX_ITEMS, compact_tool_result  # noqa: E402

PR = {
    "number": 5,
    "title": "Fix thing",
    "state": "closed",
    "merged_at": "2026-01-01T00:00:00Z",
    "html_url": "https://github.com/o/r/pull/5",
    "node_id": "PR_abc",
    "user": {"login": "dev", "avatar_url": "https://x/y.png", "id": 1},
    "labels": [{"name": "bug", "color": "ff0000", "id": 9}],
    "body": "b" * 5000,
}


def test_pr_list_keeps_only_useful_fields_and_trims_bodies():
    out = json.loads(compact_tool_result("list_pull_requests", json.dumps([PR] * 40)))
    assert len(out) == MAX_ITEMS
    first = out[0]
    assert set(first) == {"number", "title", "state", "merged_at", "author", "labels"}
    assert first["author"] == "dev" and first["labels"] == ["bug"]
    single = json.loads(compact_tool_result("get_pull_request", json.dumps(PR)))
    assert len(single["body"]) < 800 and "truncated" in single["body"]


def test_single_pr_is_slimmed():
    assert "html_url" not in compact_tool_result("get_pull_request", json.dumps(PR))


def test_non_json_and_unknown_json_are_truncated():
    long = "diff --git " + "x" * 10_000
    assert len(compact_tool_result("get_pull_request_diff", long)) < 3100
    assert compact_tool_result("get_file_contents", "short") == "short"
    blob = json.dumps({"content": "y" * 10_000})
    assert "truncated" in compact_tool_result("get_file_contents", blob)


def test_it_is_far_smaller_than_the_raw_payload():
    raw = json.dumps([PR] * 40)
    assert len(compact_tool_result("list_pull_requests", raw)) < len(raw) / 5
