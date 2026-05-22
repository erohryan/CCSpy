"""Tests for categories.py — stub, fully implemented in Phase 4."""
import pytest
from ccspy.categories import categorise, UNCATEGORISED

RULES = [
    {"category": "feature-build", "match_any": ["implement", "add ", "create"]},
    {"category": "debug", "match_any": ["fix", "bug", "broken"]},
    {"category": "planning", "match_any": ["plan", "design", "architecture"]},
]


def test_first_rule_matches():
    assert categorise("implement a login form", RULES) == "feature-build"


def test_debug_matches():
    assert categorise("fix the bug in the payment processor", RULES) == "debug"


def test_planning_matches():
    assert categorise("plan out the architecture for the gateway", RULES) == "planning"


def test_uncategorised_when_no_match():
    assert categorise("something entirely unrelated", RULES) == UNCATEGORISED


def test_case_insensitive():
    assert categorise("IMPLEMENT a feature", RULES) == "feature-build"


def test_first_match_wins():
    # Both "implement" and "fix" appear — feature-build rule comes first
    result = categorise("implement a fix for the bug", RULES)
    assert result == "feature-build"


def test_empty_text():
    assert categorise("", RULES) == UNCATEGORISED


def test_empty_rules():
    assert categorise("implement something", []) == UNCATEGORISED
