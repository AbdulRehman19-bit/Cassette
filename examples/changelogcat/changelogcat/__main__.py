"""Usage: python -m changelogcat <owner/repo> <fromTag> <toTag>  (or env REPO, FROM_TAG, TO_TAG)

Provider is chosen by env PROVIDER: `anthropic` (default, needs ANTHROPIC_API_KEY) or `groq` (needs GROQ_API_KEY).
MODEL picks the model, e.g. claude-sonnet-5-5 or openai/gpt-oss-120b.
"""

import asyncio
import os
import sys
from typing import Any

from cassette.model import maybe_wrap_model

from .agent import connect_github, run_agent

DEFAULT_MODELS = {"anthropic": "claude-sonnet-5-5", "groq": "openai/gpt-oss-120b"}


def make_client(provider: str) -> Any:
    if provider == "groq":
        from cassette.model.openai_compat import groq_client

        key = os.environ.get("GROQ_API_KEY")
        if not key and not os.environ.get("CASSETTE_REPLAY_MODEL"):
            raise SystemExit("GROQ_API_KEY is not set")
        return groq_client(key or "offline")
    if provider == "anthropic":
        from anthropic import AsyncAnthropic

        return AsyncAnthropic()
    raise SystemExit(f"unknown PROVIDER: {provider} (use anthropic or groq)")


async def main() -> int:
    args = sys.argv[1:]
    repo = args[0] if len(args) > 0 else os.environ.get("REPO")
    from_tag = args[1] if len(args) > 1 else os.environ.get("FROM_TAG")
    to_tag = args[2] if len(args) > 2 else os.environ.get("TO_TAG")
    if not (repo and from_tag and to_tag):
        print("usage: python -m changelogcat <owner/repo> <fromTag> <toTag>", file=sys.stderr)
        return 2
    provider = os.environ.get("PROVIDER", "anthropic")
    async with connect_github() as host:
        result = await run_agent(
            repo,
            from_tag,
            to_tag,
            host=host,
            client=maybe_wrap_model(make_client(provider)),
            model=os.environ.get("MODEL", DEFAULT_MODELS.get(provider, "")),
        )
    if result.stopped_by_limit:
        print("warning: stopped at step limit", file=sys.stderr)
    sys.stdout.write(result.output + "\n")
    return 0


sys.exit(asyncio.run(main()))
