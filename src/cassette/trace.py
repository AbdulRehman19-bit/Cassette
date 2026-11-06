"""The trace: an append-only JSONL file shared by every component that observes a run.

The MCP proxy process and the model wrapper (in the agent process) both append to it; the
runner folds it into a cassette when the run ends. Append order is the step order.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

TraceEvent = dict[str, Any]
"""One of:
  {"type": "model", "request", "response", "usage"?, "ms"?}
  {"type": "tool", "server", "name", "args", "result", "isError"?, "ms"?}
  {"type": "tools", "server", "tools": [{"name", "inputSchema"}]}
  {"type": "divergence", "server", "name", "args", "reason"}
"""


def append_trace(path: str | Path, event: TraceEvent) -> None:
    # One write() of one line in append mode keeps events from concurrent processes whole and ordered.
    line = json.dumps(event, ensure_ascii=False, default=_default) + "\n"
    with open(path, "a", encoding="utf-8", newline="\n") as f:
        f.write(line)


def read_trace(path: str | Path) -> list[TraceEvent]:
    p = Path(path)
    if not p.exists():
        return []
    return [json.loads(line) for line in p.read_text(encoding="utf-8").splitlines() if line.strip()]


def _default(o: Any) -> Any:
    # SDK response objects (pydantic models) serialize themselves.
    dump = getattr(o, "model_dump", None)
    if callable(dump):
        return dump(mode="json")
    raise TypeError(f"not JSON serializable: {type(o).__name__}")
