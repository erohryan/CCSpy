"""Keyword-rule-driven session categorisation.

Rules are defined in ~/.config/ccspy/categories.toml.
First match wins; matching is case-insensitive substring against the first
user message of the session.
"""
from __future__ import annotations

import tomllib
from importlib.resources import files
from pathlib import Path

from ccspy._paths import CONFIG_DIR

USER_CATEGORIES_PATH = CONFIG_DIR / "categories.toml"
UNCATEGORISED = "uncategorized"


def load_rules(path: Path | None = None) -> list[dict]:
    """Load category rules from user config, falling back to starter rules."""
    target = path or USER_CATEGORIES_PATH
    if target.exists():
        with target.open("rb") as fh:
            data = tomllib.load(fh)
        return data.get("rule", [])
    return []


def ensure_user_categories() -> None:
    """Copy starter_categories.toml to user config if it doesn't exist."""
    if USER_CATEGORIES_PATH.exists():
        return
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    starter = files("ccspy") / "data" / "starter_categories.toml"
    USER_CATEGORIES_PATH.write_bytes(starter.read_bytes())


def categorise(text: str, rules: list[dict]) -> str:
    """Return the first matching category name, or UNCATEGORISED.

    Args:
        text: The first user message text (case-insensitive matching).
        rules: List of rule dicts with 'category' and 'match_any' keys.
    """
    lower = text.lower()
    for rule in rules:
        for keyword in rule.get("match_any", []):
            if keyword.lower() in lower:
                return rule["category"]
    return UNCATEGORISED
