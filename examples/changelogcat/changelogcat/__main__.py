"""Usage: python -m changelogcat <owner/repo> <fromTag> <toTag>  (or env REPO, FROM_TAG, TO_TAG)"""

import asyncio
import os
import sys

from anthropic import AsyncAnthropic

from cassette.model import maybe_wrap_model

from .agent import connect_github, run_agent


async def main() -> int:
    args = sys.argv[1:]
    repo = args[0] if len(args) > 0 else os.environ.get("REPO")
    from_tag = args[1] if len(args) > 1 else os.environ.get("FROM_TAG")
    to_tag = args[2] if len(args) > 2 else os.environ.get("TO_TAG")
    if not (repo and from_tag and to_tag):
        print("usage: python -m changelogcat <owner/repo> <fromTag> <toTag>", file=sys.stderr)
        return 2
    async with connect_github() as host:
        result = await run_agent(
            repo,
            from_tag,
            to_tag,
            host=host,
            client=maybe_wrap_model(AsyncAnthropic()),
            model=os.environ.get("MODEL", "claude-sonnet-5-5"),
        )
    if result.stopped_by_limit:
        print("warning: stopped at step limit", file=sys.stderr)
    sys.stdout.write(result.output + "\n")
    return 0


sys.exit(asyncio.run(main()))
