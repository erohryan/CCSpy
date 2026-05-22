"""Token-to-api-equiv cost conversion.

Reads pricing.toml (shipped with the package). If a model is not in the table,
returns None rather than 0 — zero would be misleading.

All dollar figures are labelled "api-equiv". Pro/Max subscribers pay flat rate;
these numbers represent what the same usage would cost on the pay-as-you-go API.
"""
from __future__ import annotations

import tomllib
from functools import lru_cache
from importlib.resources import files
from typing import Optional


@lru_cache(maxsize=1)
def _load_table() -> dict:
    """Load pricing.toml from the package data directory."""
    data_path = files("ccspy") / "data" / "pricing.toml"
    with data_path.open("rb") as fh:
        return tomllib.load(fh)


def get_model_pricing(model_id: str) -> Optional[dict]:
    """Return the pricing dict for a model_id, or None if unknown."""
    table = _load_table()
    models = table.get("models", {})
    if model_id in models:
        return models[model_id]
    # Try stripping a trailing date suffix: claude-sonnet-4-5-20250929 → claude-sonnet-4-5
    parts = model_id.rsplit("-", 1)
    if len(parts) == 2 and parts[1].isdigit() and len(parts[1]) == 8:
        return models.get(parts[0])
    return None


def compute_cost(
    model_id: str,
    input_tokens: int,
    output_tokens: int,
    cache_creation_tokens: int = 0,
    cache_read_tokens: int = 0,
    cache_creation_1h_tokens: int = 0,
    cache_creation_5m_tokens: int = 0,
) -> Optional[float]:
    """Return api-equiv USD cost, or None if model pricing is unknown."""
    pricing = get_model_pricing(model_id)
    if pricing is None:
        return None

    inp_rate = pricing.get("input_per_mtok", 0)
    out_rate = pricing.get("output_per_mtok", 0)
    cw5m_rate = pricing.get("cache_write_5m_per_mtok", 0)
    cw1h_rate = pricing.get("cache_write_1h_per_mtok", 0)
    cr_rate = pricing.get("cache_read_per_mtok", 0)

    # If we have the breakdown, use differentiated rates.
    if cache_creation_1h_tokens or cache_creation_5m_tokens:
        remaining_cc = cache_creation_tokens - cache_creation_1h_tokens - cache_creation_5m_tokens
        cc_cost = (
            cache_creation_5m_tokens * cw5m_rate
            + cache_creation_1h_tokens * cw1h_rate
            + max(0, remaining_cc) * cw5m_rate  # default to 5m rate for unattributed
        ) / 1_000_000
    else:
        cc_cost = cache_creation_tokens * cw5m_rate / 1_000_000

    total = (
        input_tokens * inp_rate / 1_000_000
        + output_tokens * out_rate / 1_000_000
        + cc_cost
        + cache_read_tokens * cr_rate / 1_000_000
    )
    return round(total, 6)


def pricing_updated() -> str:
    """Return the _meta.updated date from pricing.toml."""
    table = _load_table()
    return table.get("_meta", {}).get("updated", "unknown")
