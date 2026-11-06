"""The static HTML report: one self-contained file (inline CSS, no JavaScript, no network), openable from a CI artifact."""

from __future__ import annotations

import difflib
import json
from html import escape as e
from typing import Any

from .markdown import fmt_call, summary_line

CSS = """
:root{--bg:#fff;--fg:#1c1b1a;--muted:#6b6963;--card:#faf9f7;--line:#e4e1da;--ok:#1a7f4b;--okbg:#e6f4ec;
--bad:#b42318;--badbg:#fdeceb;--warn:#8a5a00;--warnbg:#fff4dc;--info:#1f5fae;--infobg:#e8f0fb;--mono:ui-monospace,Consolas,monospace}
@media (prefers-color-scheme:dark){:root{--bg:#161513;--fg:#ece9e3;--muted:#9a968d;--card:#1e1d1a;--line:#34322d;
--ok:#4cc38a;--okbg:#14301f;--bad:#ff8b80;--badbg:#3a1613;--warn:#f2b84b;--warnbg:#33260b;--info:#7db2f5;--infobg:#142a47}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--fg);font:15px/1.5 system-ui,Segoe UI,sans-serif}
main{max-width:1100px;margin:0 auto;padding:24px 16px 64px}h1{font-size:1.5rem;margin:0 0 4px}
h2{font-size:1.1rem;margin:0}h3{font-size:.8rem;text-transform:uppercase;letter-spacing:.06em;color:var(--muted);margin:20px 0 8px}
code,pre{font-family:var(--mono);font-size:.82rem}pre{margin:0;white-space:pre-wrap;word-break:break-word}
.muted{color:var(--muted)}.banner{padding:12px 14px;border-radius:8px;margin:12px 0 20px;font-weight:600}
.banner.ok{background:var(--okbg);color:var(--ok)}.banner.bad{background:var(--badbg);color:var(--bad)}
.card{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:16px;margin:16px 0}
.head{display:flex;flex-wrap:wrap;gap:8px 12px;align-items:center}.badge{font-size:.75rem;font-weight:700;padding:2px 8px;border-radius:99px}
.badge.ok{background:var(--okbg);color:var(--ok)}.badge.bad{background:var(--badbg);color:var(--bad)}
.badge.attack{background:var(--warnbg);color:var(--warn)}
.chips{display:flex;flex-wrap:wrap;gap:6px;margin-top:10px}.chip{border:1px solid var(--line);border-radius:6px;padding:2px 8px;font-size:.8rem}
.callout{background:var(--warnbg);color:var(--warn);border-radius:8px;padding:8px 12px;margin-top:12px;font-weight:600}
.traj{display:grid;grid-template-columns:1fr 1fr;gap:6px}.colhead{font-size:.75rem;color:var(--muted);font-weight:600}
.cell{border:1px solid var(--line);border-radius:6px;padding:6px 8px;min-width:0;background:var(--bg)}
.cell summary{cursor:pointer;list-style:none;overflow-wrap:anywhere}.cell summary::-webkit-details-marker{display:none}
.cell pre{margin-top:6px;max-height:260px;overflow:auto;color:var(--muted)}
.empty{border:1px dashed var(--line);border-radius:6px;color:var(--muted);padding:6px 8px;font-size:.8rem}
.removed{background:var(--badbg);border-color:var(--bad)}.added{background:var(--okbg);border-color:var(--ok)}
.changed{background:var(--warnbg);border-color:var(--warn)}.same{opacity:.75}.resultchanged{background:var(--infobg);border-color:var(--info)}
.tag{font-weight:700;margin-right:6px}.delta{display:block;color:var(--muted);font-size:.78rem;margin-top:2px}
ul.checks{list-style:none;margin:0;padding:0}ul.checks li{padding:3px 0}.fail{color:var(--bad)}.pass{color:var(--ok)}
.out{display:grid;grid-template-columns:1fr 1fr;gap:6px}.out .cell{white-space:pre-wrap;font-family:var(--mono);font-size:.82rem}
@media (max-width:700px){.traj,.out{grid-template-columns:1fr}}
"""

TAGS = {"removed": "−", "added": "+", "changed": "~", "same": "", "resultchanged": "≈"}
KIND_CLASS = {
    "tool_removed": "removed",
    "tool_added": "added",
    "tool_args_changed": "changed",
    "same": "same",
    "result_changed": "resultchanged",
}


def _cell(step: dict[str, Any] | None, cls: str, delta: str = "") -> str:
    if step is None:
        return '<div class="empty">no call</div>'
    body = f"<b>args</b>\n{json.dumps(step['args'], indent=2, ensure_ascii=False)}\n\n<b>result</b>\n{step['result']}"
    note = f'<span class="delta">{e(delta)}</span>' if delta else ""
    err = " (error)" if step["isError"] else ""
    return (
        f'<details class="cell {cls}"><summary><span class="tag">{TAGS.get(cls, "")}</span>'
        f"<code>step {step['i']} · {e(fmt_call(step))}</code>{err}{note}</summary><pre>{e(body)}</pre></details>"
    )


def _pair_swaps(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Show a removed call and the added call that replaced it on one row, side by side."""
    out: list[dict[str, Any]] = []
    i = 0
    while i < len(rows):
        row = rows[i]
        nxt = rows[i + 1] if i + 1 < len(rows) else None
        if row["kind"] == "tool_removed" and nxt and nxt["kind"] == "tool_added":
            out.append({"kind": "swap", "base": row["base"], "new": nxt["new"]})
            i += 2
        else:
            out.append(row)
            i += 1
    return out


def _trajectory(rows: list[dict[str, Any]]) -> str:
    cells = ['<div class="colhead">Baseline</div><div class="colhead">This run</div>']
    for row in _pair_swaps(rows):
        if row["kind"] == "swap":
            cells += [_cell(row["base"], "removed"), _cell(row["new"], "added")]
            continue
        cls = KIND_CLASS[row["kind"]]
        cells.append(_cell(row["base"], cls if cls != "added" else "same", row.get("delta", "")))
        cells.append(_cell(row["new"], cls if cls != "removed" else "same", row.get("delta", "")))
    return f'<div class="traj">{"".join(cells)}</div>'


def _output_diff(base: str, new: str) -> str:
    a, b = base.splitlines(), new.splitlines()
    left: list[str] = []
    right: list[str] = []
    for op, i1, i2, j1, j2 in difflib.SequenceMatcher(None, a, b, autojunk=False).get_opcodes():
        if op == "equal":
            left += [f"  {x}" for x in a[i1:i2]]
            right += [f"  {x}" for x in b[j1:j2]]
        else:
            left += [f"− {x}" for x in a[i1:i2]]
            right += [f"+ {x}" for x in b[j1:j2]]
    cls_l = "cell removed" if a != b else "cell"
    cls_r = "cell added" if a != b else "cell"
    return (
        f'<div class="colhead">Baseline output</div><div class="colhead">This run\'s output</div>'
        f'<div class="out" style="grid-column:1/-1"><div class="{cls_l}">{e(chr(10).join(left)) or "(empty)"}</div>'
        f'<div class="{cls_r}">{e(chr(10).join(right)) or "(empty)"}</div></div>'
    )


def _delta(old: float, new: float, fmt: str = "{:,.0f}") -> str:
    d = new - old
    pct = f" ({d / old * 100:+.0f}%)" if old else ""
    return f"{fmt.format(old)} → {fmt.format(new)}{pct}"


def _chips(sc: dict[str, Any]) -> str:
    b, n = sc["totals"]["base"], sc["totals"]["new"]
    chips = [
        f"tool calls {b['toolCalls']} → {n['toolCalls']}",
        f"tokens {_delta(b['tokensIn'] + b['tokensOut'], n['tokensIn'] + n['tokensOut'])}",
        f"latency {_delta(b['latencyMs'], n['latencyMs'])} ms",
        f"output similarity {sc['outputSimilarity']:.2f}",
    ]
    if b["costUsd"] is not None and n["costUsd"] is not None:
        chips.insert(2, f"cost {_delta(b['costUsd'], n['costUsd'], '${:.4f}')}")
    if b["model"] and n["model"] and b["model"] != n["model"]:
        chips.append(f"model {e(b['model'])} → {e(n['model'])}")
    elif n["model"] and not b["model"]:
        chips.append(f"model {e(n['model'])}")
    return '<div class="chips">' + "".join(f'<span class="chip">{c}</span>' for c in chips) + "</div>"


def _assertions(items: list[dict[str, Any]]) -> str:
    if not items:
        return ""
    lis = []
    for a in items:
        if a["skipped"]:
            lis.append(f'<li class="muted">– {e(a["name"])}: skipped ({e(a["skipped"])})</li>')
        elif a["ok"]:
            lis.append(f'<li><span class="pass">✓ pass</span> <code>{e(a["name"])}</code></li>')
        else:
            msgs = "; ".join(e(m) for m in a["failures"])
            lis.append(f'<li><span class="fail">× fail</span> <code>{e(a["name"])}</code>: {msgs}</li>')
    return f'<h3>Assertions</h3><ul class="checks">{"".join(lis)}</ul>'


def _scenario(sc: dict[str, Any]) -> str:
    badge = '<span class="badge ok">PASS</span>' if sc["ok"] else '<span class="badge bad">FAIL</span>'
    attack = '<span class="badge attack">attack scenario</span>' if sc["attack"] else ""
    callout = ""
    if sc["behaviorChangedButOutputFine"]:
        callout = (
            f'<div class="callout">The output looks fine (similarity {sc["outputSimilarity"]:.2f}) '
            "but the agent's behavior changed.</div>"
        )
    notes = "".join(f'<p class="fail">{e(d)}</p>' for d in sc["divergences"])
    return (
        f'<section class="card" id="{e(sc["name"])}"><div class="head"><h2>{e(sc["name"])}</h2>{badge}{attack}</div>'
        f"{_chips(sc)}{callout}{notes}"
        f"<h3>Trajectory</h3>{_trajectory(sc['rows']) if sc['rows'] else '<p class=muted>No tool calls.</p>'}"
        f"{_assertions(sc['assertions'])}"
        f'<h3>Final output</h3><div class="traj">{_output_diff(sc["output"]["base"], sc["output"]["new"])}</div>'
        "</section>"
    )


def render_html(report: dict[str, Any]) -> str:
    s = report["summary"]
    cls = "ok" if report["passed"] else "bad"
    mode = "offline (recorded model)" if report["offline"] else "live model, recorded tools"
    if report.get("modelOverride"):
        mode += f" · model: {report['modelOverride']}"
    body = "".join(_scenario(sc) for sc in report["scenarios"])
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Cassette report</title><style>{CSS}</style></head><body><main>
<h1>Cassette report</h1>
<div class="muted">{e(report["generatedAt"])} · {e(mode)} · {s["scenarios"]} scenario(s)</div>
<div class="banner {cls}">{"Passed" if report["passed"] else "Failed"}: {e(summary_line(report))}</div>
{body}
</main></body></html>
"""
