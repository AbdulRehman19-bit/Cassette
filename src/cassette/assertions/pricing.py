"""USD per million tokens `(input, output)`, used by `max_cost_usd`.

These are rough defaults, not a price list: providers change prices. Override or extend them with the top-level
`pricing:` map in cassette.yaml. A model with no price makes `max_cost_usd` fail loudly instead of guessing.
"""

from __future__ import annotations

DEFAULT_PRICING: dict[str, tuple[float, float]] = {
    "openai/gpt-oss-120b": (0.15, 0.60),
    "openai/gpt-oss-20b": (0.075, 0.30),
    "claude-sonnet": (3.0, 15.0),
    "claude-haiku": (1.0, 5.0),
    "claude-opus": (5.0, 25.0),
}


def price_for(model: str | None, overrides: dict[str, list[float]] | None = None) -> tuple[float, float] | None:
    """Exact model id first, then the longest matching prefix (so `claude-sonnet-5-5` finds `claude-sonnet`)."""
    if not model:
        return None
    table: dict[str, tuple[float, float]] = dict(DEFAULT_PRICING)
    for k, v in (overrides or {}).items():
        table[k] = (float(v[0]), float(v[1]))
    if model in table:
        return table[model]
    hits = [k for k in table if model.startswith(k)]
    return table[max(hits, key=len)] if hits else None
