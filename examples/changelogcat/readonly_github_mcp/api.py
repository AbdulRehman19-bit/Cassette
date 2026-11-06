"""Read-only GitHub access for the four tools ChangelogCat needs. GET requests only, by construction."""

from __future__ import annotations

import base64
from typing import Any

import httpx

API = "https://api.github.com"
MAX_TEXT = 20_000
MAX_PR_PAGES = 5  # when filtering by tags we scan at most this many pages of 100 closed PRs


class GitHubError(Exception):
    pass


def _trim(text: str, limit: int = MAX_TEXT) -> str:
    return text if len(text) <= limit else text[:limit] + f"\n... [truncated {len(text) - limit} chars]"


def _slim_pr(pr: dict[str, Any], *, detail: bool = False) -> dict[str, Any]:
    out: dict[str, Any] = {
        "number": pr["number"],
        "title": pr["title"],
        "state": pr["state"],
        "merged_at": pr.get("merged_at"),
        "author": (pr.get("user") or {}).get("login"),
        "labels": [lb["name"] for lb in pr.get("labels") or []],
        "html_url": pr.get("html_url"),
    }
    if detail:
        out["body"] = pr.get("body") or ""
        for k in ("changed_files", "additions", "deletions", "base", "head"):
            if k in pr:
                out[k] = pr[k]["ref"] if k in ("base", "head") else pr[k]
    return out


class GitHub:
    def __init__(self, token: str = "", *, base_url: str = API, client: httpx.AsyncClient | None = None) -> None:
        headers = {"Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28"}
        if token:
            headers["Authorization"] = f"Bearer {token}"
        self._http = client or httpx.AsyncClient(base_url=base_url, headers=headers, timeout=30)

    async def _get(self, path: str, *, accept: str | None = None, **params: Any) -> httpx.Response:
        res = await self._http.get(path, params={k: v for k, v in params.items() if v is not None},
                                   headers={"Accept": accept} if accept else None)  # fmt: skip
        if res.status_code >= 400:
            try:
                msg = res.json().get("message", res.reason_phrase)
            except ValueError:
                msg = res.reason_phrase
            raise GitHubError(f"GitHub {res.status_code}: {msg} ({path})")
        return res

    async def _shas_between(self, owner: str, repo: str, from_ref: str, to_ref: str) -> set[str]:
        """Commits in `to_ref` but not `from_ref`: the (squash-)merge commits of PRs shipped in that release."""
        shas: set[str] = set()
        page = 1
        while True:
            data = (
                await self._get(f"/repos/{owner}/{repo}/compare/{from_ref}...{to_ref}", per_page=100, page=page)
            ).json()
            shas |= {c["sha"] for c in data.get("commits", [])}
            if len(data.get("commits", [])) < 100 or page >= 10:
                return shas
            page += 1

    async def list_pull_requests(
        self,
        owner: str,
        repo: str,
        state: str = "closed",
        from_ref: str | None = None,
        to_ref: str | None = None,
        per_page: int = 30,
        page: int = 1,
    ) -> list[dict[str, Any]]:
        """PRs, slimmed. With `from_ref` and `to_ref`, only PRs merged between those two tags/refs."""
        if bool(from_ref) != bool(to_ref):
            raise GitHubError("from_ref and to_ref must be given together")
        if not (from_ref and to_ref):
            prs = (
                await self._get(
                    f"/repos/{owner}/{repo}/pulls",
                    state=state,
                    sort="updated",
                    direction="desc",
                    per_page=per_page,
                    page=page,
                )
            ).json()
            return [_slim_pr(p) for p in prs]
        shas = await self._shas_between(owner, repo, from_ref, to_ref)
        found: list[dict[str, Any]] = []
        for p in range(1, MAX_PR_PAGES + 1):
            prs = (
                await self._get(
                    f"/repos/{owner}/{repo}/pulls",
                    state="closed",
                    sort="updated",
                    direction="desc",
                    per_page=100,
                    page=p,
                )
            ).json()
            found += [_slim_pr(x) for x in prs if x.get("merged_at") and x.get("merge_commit_sha") in shas]
            if len(prs) < 100:
                break
        return sorted(found, key=lambda x: x["merged_at"])

    async def get_pull_request(self, owner: str, repo: str, pull_number: int) -> dict[str, Any]:
        data = (await self._get(f"/repos/{owner}/{repo}/pulls/{pull_number}")).json()
        out = _slim_pr(data, detail=True)
        out["body"] = _trim(out["body"], 4000)
        return out

    async def get_pull_request_diff(self, owner: str, repo: str, pull_number: int) -> str:
        res = await self._get(f"/repos/{owner}/{repo}/pulls/{pull_number}", accept="application/vnd.github.diff")
        return _trim(res.text)

    async def get_file_contents(self, owner: str, repo: str, path: str, ref: str | None = None) -> str:
        data = (await self._get(f"/repos/{owner}/{repo}/contents/{path.lstrip('/')}", ref=ref)).json()
        if isinstance(data, list):  # a directory
            return "\n".join(f"{e['type']}\t{e['path']}" for e in data)
        if data.get("encoding") == "base64":
            return _trim(base64.b64decode(data["content"]).decode("utf-8", "replace"))
        return _trim(str(data.get("content", "")))

    async def aclose(self) -> None:
        await self._http.aclose()
