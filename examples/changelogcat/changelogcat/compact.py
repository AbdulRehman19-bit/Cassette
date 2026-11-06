"""Shrink tool results before the model sees them.

GitHub's JSON is verbose (URLs, node ids, avatar links) and a handful of PRs can run to tens of thousands of tokens,
which blows small context/TPM budgets. The recorded cassette keeps the full raw result; only what goes back to the
model is trimmed, so the agent's behavior stays deterministic given the same tool output.
"""

from __future__ import annotations

import json
from typing import Any

MAX_RESULT_CHARS = 3000
MAX_BODY_CHARS = 700
MAX_ITEMS = 25

_PR_KEYS = ("number", "title", "state", "merged_at", "draft")


def _trim(text: str, limit: int) -> str:
    return text if len(text) <= limit else text[:limit] + f"... [truncated {len(text) - limit} chars]"


def _slim_pr(pr: dict[str, Any], *, body: bool) -> dict[str, Any]:
    out = {k: pr[k] for k in _PR_KEYS if k in pr}
    if isinstance(pr.get("user"), dict) and pr["user"].get("login"):
        out["author"] = pr["user"]["login"]
    labels = [lb.get("name") for lb in pr.get("labels") or [] if isinstance(lb, dict)]
    if labels:
        out["labels"] = labels
    if body and isinstance(pr.get("body"), str) and pr["body"]:
        out["body"] = _trim(pr["body"], MAX_BODY_CHARS)
    return out


def compact_tool_result(name: str, text: str) -> str:
    """Return a smaller version of a tool result, JSON-aware for PR payloads, plain truncation otherwise."""
    try:
        data = json.loads(text)
    except ValueError:
        return _trim(text, MAX_RESULT_CHARS)
    if isinstance(data, list) and data and all(isinstance(x, dict) and "number" in x for x in data):
        data = [_slim_pr(x, body=False) for x in data[:MAX_ITEMS]]  # titles suffice to pick PRs to open
    elif isinstance(data, dict) and "number" in data and "title" in data:
        data = _slim_pr(data, body=True)
    else:
        return _trim(text, MAX_RESULT_CHARS)
    return _trim(json.dumps(data, ensure_ascii=False, separators=(",", ":")), MAX_RESULT_CHARS * 2)
