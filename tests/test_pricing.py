"""Tests for pricing.py."""
from ccspy.pricing import get_model_pricing, compute_cost, pricing_updated


def test_known_model_returns_pricing():
    p = get_model_pricing("claude-sonnet-4-6")
    assert p is not None
    assert p["input_per_mtok"] == 3.00
    assert p["output_per_mtok"] == 15.00
    assert p["cache_read_per_mtok"] == 0.30


def test_haiku_pricing():
    p = get_model_pricing("claude-haiku-4-5-20251001")
    assert p is not None
    assert p["input_per_mtok"] == 1.00


def test_unknown_model_returns_none():
    assert get_model_pricing("claude-made-up-99") is None


def test_compute_cost_known_model():
    # 1M input + 1M output on Haiku 4.5 = $1.00 + $5.00 = $6.00
    cost = compute_cost("claude-haiku-4-5-20251001", input_tokens=1_000_000, output_tokens=1_000_000)
    assert cost == pytest.approx(6.00, rel=1e-4)


def test_compute_cost_cache_read():
    # 1M cache read on Haiku 4.5 = $0.10
    cost = compute_cost("claude-haiku-4-5-20251001", input_tokens=0, output_tokens=0, cache_read_tokens=1_000_000)
    assert cost == pytest.approx(0.10, rel=1e-4)


def test_compute_cost_unknown_model_returns_none():
    cost = compute_cost("claude-made-up-99", input_tokens=1000, output_tokens=1000)
    assert cost is None


def test_pricing_updated_is_string():
    d = pricing_updated()
    assert isinstance(d, str)
    assert len(d) == 10  # YYYY-MM-DD


import pytest
