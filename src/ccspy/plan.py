"""Subscription plan config and break-even calculation."""
from __future__ import annotations

from ccspy import identity

# (key, display_name, monthly_cost_usd)
PLANS: list[tuple[str, str, float]] = [
    ("free",    "Free",     0.0),
    ("pro",     "Pro",     20.0),
    ("max_5x",  "Max 5x",  100.0),
    ("max_20x", "Max 20x", 200.0),
]


def get_plan_config() -> dict:
    return identity.read_section("plan")


def get_monthly_cost() -> float | None:
    cfg = get_plan_config()
    cost = cfg.get("monthly_cost")
    return float(cost) if cost is not None else None


def get_plan_name() -> str:
    return get_plan_config().get("name", "")


def set_plan(name: str, monthly_cost: float) -> None:
    identity.update_section("plan", {"name": name, "monthly_cost": monthly_cost})


def quota_for_range(monthly_cost: float, range_days: int) -> float:
    """Pro-rated API-equiv quota for the given range.

    Uses 30-day month as the base. range_days=0 means today (1 day).
    """
    days = range_days if range_days > 0 else 1
    return monthly_cost / 30 * days


def break_even_pct(cost_usd: float, monthly_cost: float, range_days: int) -> float | None:
    if monthly_cost <= 0:
        return None
    quota = quota_for_range(monthly_cost, range_days)
    return cost_usd / quota * 100 if quota > 0 else None
