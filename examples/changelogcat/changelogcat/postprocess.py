"""Defense in depth: whatever the model wrote, links that don't point into the repository never reach a release.

A prompt-injected PR can ask the notes to include "download the fix at https://evil.example". The system prompt tells
the model not to, but a prompt is a request, not a guarantee; this step is the guarantee.
"""

from __future__ import annotations

import re

_MD_LINK = re.compile(r"(!?)\[([^\]]*)\]\(\s*<?([^)\s>]+)>?[^)]*\)")
_AUTOLINK = re.compile(r"<(https?://[^>\s]+)>")
_BARE_URL = re.compile(r"https?://[^\s<>\"')\]]+")


def _is_repo_url(url: str, repo: str) -> bool:
    m = re.match(r"https?://(?:www\.)?github\.com/([^/]+)/([^/#?]+)", url, re.IGNORECASE)
    return bool(m) and f"{m.group(1)}/{m.group(2)}".lower() == repo.lower()


def strip_foreign_links(text: str, repo: str) -> str:
    """Keep links into `owner/repo` (and relative links); replace others with their text or drop them."""

    def md(m: re.Match[str]) -> str:
        bang, label, url = m.groups()
        if not re.match(r"[a-zA-Z][a-zA-Z0-9+.-]*:", url) or _is_repo_url(url, repo):
            return m.group(0)
        return "" if bang else label  # drop images, keep a link's visible text

    text = _MD_LINK.sub(md, text)
    text = _AUTOLINK.sub(lambda m: m.group(0) if _is_repo_url(m.group(1), repo) else "", text)

    def bare(m: re.Match[str]) -> str:
        url = m.group(0).rstrip(".,;:!?")
        return m.group(0) if _is_repo_url(url, repo) else ""

    # Bare URLs that survived the steps above and are not inside a repo link.
    out = _BARE_URL.sub(bare, text)
    return re.sub(r"[ \t]+\n", "\n", out).strip() + ("\n" if text.endswith("\n") else "")
