"""Report output: `results.json` (the data), `index.html` (static report) and `comment.md` (PR comment)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .data import build_report
from .html import render_html
from .markdown import MARKER, render_comment, summary_line

DEFAULT_DIR = "cassette-report"


def write_report(report: dict[str, Any], directory: str | Path, report_url: str | None = None) -> dict[str, Path]:
    d = Path(directory)
    d.mkdir(parents=True, exist_ok=True)
    paths = {"json": d / "results.json", "html": d / "index.html", "comment": d / "comment.md"}
    paths["json"].write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    paths["html"].write_text(render_html(report), encoding="utf-8")
    paths["comment"].write_text(render_comment(report, report_url), encoding="utf-8")
    return paths


def load_report(directory: str | Path) -> dict[str, Any]:
    data: dict[str, Any] = json.loads((Path(directory) / "results.json").read_text(encoding="utf-8"))
    return data


__all__ = [
    "DEFAULT_DIR",
    "MARKER",
    "build_report",
    "load_report",
    "render_comment",
    "render_html",
    "summary_line",
    "write_report",
]
