"""Strip volatile values so two runs that differ only in timestamps, ids or key order serialize identically."""

from __future__ import annotations

import json
import re
from typing import Any

TS = "<timestamp>"
ID = "<id>"

_ISO_TS = re.compile(r"\b\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:?\d{2})\b")
_UUID = re.compile(r"\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b", re.IGNORECASE)
# Provider-issued ids: Anthropic (msg_, toolu_, req_), OpenAI (chatcmpl-, call_, resp_).
_PROVIDER_ID = re.compile(r"\b(?:msg_|toolu_|req_|chatcmpl-|call_|resp_)[A-Za-z0-9]{6,}\b")


def normalize_string(s: str) -> str:
    return _PROVIDER_ID.sub(ID, _UUID.sub(ID, _ISO_TS.sub(TS, s)))


def normalize(value: Any) -> Any:
    """Deep-normalize a JSON value: volatile substrings become placeholders and object keys are sorted."""
    if isinstance(value, str):
        return normalize_string(value)
    if isinstance(value, list):
        return [normalize(v) for v in value]
    if isinstance(value, dict):
        return {k: normalize(value[k]) for k in sorted(value)}
    return value


def dumps(value: Any) -> str:
    return json.dumps(value, separators=(",", ":"), ensure_ascii=False)


def canonical_args(args: Any) -> str:
    """Stable string form of normalized args, used as the exact-match key."""
    return dumps(normalize(args if args is not None else {}))
