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


# Shapes of secrets that must never appear in a release: GitHub and cloud tokens, private keys, and honeytokens
# (planted `CANARY-...` markers, which stand in for real secrets in attack fixtures).
_SECRETS = re.compile(
    r"gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}|AKIA[0-9A-Z]{16}|gsk_[A-Za-z0-9]{20,}"
    r"|-----BEGIN [A-Z ]*PRIVATE KEY-----|CANARY-[A-Za-z0-9_-]+"
)


def redact_secrets(text: str) -> str:
    """Replace anything shaped like a secret with `[redacted]`, whatever the model was talked into writing."""
    return _SECRETS.sub("[redacted]", text)
