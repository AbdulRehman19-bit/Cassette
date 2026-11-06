import base64
import json
import sys
from pathlib import Path

import httpx
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from mcp.shared.memory import create_connected_server_and_client_session  # noqa: E402

from readonly_github_mcp.api import MAX_TEXT, GitHub, GitHubError  # noqa: E402
from readonly_github_mcp.server import TOOL_NAMES, build_server  # noqa: E402


def pr(number, merged_at=None, sha=None, state="closed", body="body"):
    return {
        "number": number,
        "title": f"PR {number}",
        "state": state,
        "merged_at": merged_at,
        "merge_commit_sha": sha,
        "user": {"login": "dev", "avatar_url": "x"},
        "labels": [{"name": "bug", "color": "f00"}],
        "html_url": f"https://github.com/o/r/pull/{number}",
        "body": body,
        "changed_files": 2,
        "additions": 5,
        "deletions": 1,
        "base": {"ref": "main"},
        "head": {"ref": f"feat-{number}"},
    }


def make_gh(handler):
    seen: list[httpx.Request] = []

    def wrapped(req: httpx.Request) -> httpx.Response:
        seen.append(req)
        return handler(req)

    client = httpx.AsyncClient(base_url="https://api.github.com", transport=httpx.MockTransport(wrapped))
    return GitHub(client=client), seen


def routes(req: httpx.Request) -> httpx.Response:
    p = req.url.path
    if p.endswith("/compare/v1...v2"):
        return httpx.Response(200, json={"commits": [{"sha": "aaa"}, {"sha": "bbb"}]})
    if p == "/repos/o/r/pulls":
        return httpx.Response(
            200,
            json=[
                pr(9, "2026-02-03T00:00:00Z", "bbb"),  # merged in range
                pr(8, None, None),  # closed, never merged
                pr(7, "2026-01-02T00:00:00Z", "aaa"),  # merged in range
                pr(3, "2025-12-01T00:00:00Z", "old"),  # merged before the range
            ],
        )
    if p == "/repos/o/r/pulls/7":
        if "diff" in req.headers["accept"]:
            return httpx.Response(200, text="diff --git a/x b/x\n+hello\n")
        return httpx.Response(200, json=pr(7, "2026-01-02T00:00:00Z", "aaa", body="x" * 9000))
    if p == "/repos/o/r/contents/README.md":
        return httpx.Response(200, json={"encoding": "base64", "content": base64.b64encode("héllo".encode()).decode()})
    if p == "/repos/o/r/contents/docs":
        return httpx.Response(200, json=[{"type": "file", "path": "docs/a.md"}, {"type": "dir", "path": "docs/img"}])
    return httpx.Response(404, json={"message": "Not Found"})


async def test_list_pull_requests_plain_is_slimmed():
    gh, _ = make_gh(routes)
    out = await gh.list_pull_requests("o", "r")
    assert [p["number"] for p in out] == [9, 8, 7, 3]
    assert set(out[0]) == {"number", "title", "state", "merged_at", "author", "labels", "html_url"}
    assert out[0]["author"] == "dev" and out[0]["labels"] == ["bug"]


async def test_list_pull_requests_between_tags_keeps_only_merged_prs_in_range_oldest_first():
    gh, seen = make_gh(routes)
    out = await gh.list_pull_requests("o", "r", from_ref="v1", to_ref="v2")
    assert [p["number"] for p in out] == [7, 9]
    assert all(r.method == "GET" for r in seen)


async def test_tag_filter_needs_both_refs():
    gh, _ = make_gh(routes)
    with pytest.raises(GitHubError, match="together"):
        await gh.list_pull_requests("o", "r", from_ref="v1")


async def test_get_pull_request_trims_the_body_and_adds_detail():
    gh, _ = make_gh(routes)
    out = await gh.get_pull_request("o", "r", 7)
    assert len(out["body"]) < 4100 and "truncated" in out["body"]
    assert out["changed_files"] == 2 and out["base"] == "main" and out["head"] == "feat-7"


async def test_get_pull_request_diff_asks_for_the_diff_media_type():
    gh, seen = make_gh(routes)
    assert "+hello" in await gh.get_pull_request_diff("o", "r", 7)
    assert seen[0].headers["accept"] == "application/vnd.github.diff"


async def test_get_file_contents_decodes_files_and_lists_directories():
    gh, _ = make_gh(routes)
    assert await gh.get_file_contents("o", "r", "README.md") == "héllo"
    assert await gh.get_file_contents("o", "r", "docs") == "file\tdocs/a.md\ndir\tdocs/img"


async def test_large_text_is_truncated():
    gh, _ = make_gh(
        lambda r: httpx.Response(200, json={"encoding": "base64", "content": base64.b64encode(b"y" * 50_000).decode()})
    )
    out = await gh.get_file_contents("o", "r", "big.txt")
    assert len(out) < MAX_TEXT + 100 and "truncated" in out


async def test_http_errors_become_readable_github_errors():
    gh, _ = make_gh(routes)
    with pytest.raises(GitHubError, match="404: Not Found"):
        await gh.get_pull_request("o", "r", 12345)


async def test_the_server_lists_exactly_the_four_read_tools_and_reports_errors_as_tool_errors():
    gh, _ = make_gh(routes)
    async with create_connected_server_and_client_session(build_server(gh)) as client:
        names = {t.name for t in (await client.list_tools()).tools}
        assert (
            names
            == TOOL_NAMES
            == {"list_pull_requests", "get_pull_request", "get_pull_request_diff", "get_file_contents"}
        )
        ok = await client.call_tool("get_pull_request", {"owner": "o", "repo": "r", "pull_number": 7})
        assert not ok.isError and json.loads(ok.content[0].text)["number"] == 7
        missing = await client.call_tool("get_pull_request", {"owner": "o", "repo": "r", "pull_number": 999})
        assert missing.isError and "404" in missing.content[0].text
        bad = await client.call_tool("get_pull_request", {"owner": "o"})
        assert bad.isError and "Error" in bad.content[0].text
        write = await client.call_tool("create_issue", {"owner": "o", "repo": "r", "title": "x"})
        assert write.isError and "unknown tool" in write.content[0].text
