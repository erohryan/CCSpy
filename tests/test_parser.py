"""Tests for parser.py — stub, fully implemented in Phase 3."""
from pathlib import Path
import pytest

FIXTURES = Path(__file__).parent / "fixtures"


def test_clean_session_parses():
    """A well-formed session should yield one session and deduplicated turns."""
    from ccspy.parser import parse_file

    session, turns, _ = parse_file(FIXTURES / "fixture_clean.jsonl")
    assert session is not None
    assert session.session_id == "aaaa0001-0000-0000-0000-000000000001"
    # Two unique requestIds → two turns
    assert len(turns) == 2
    # First turn captured Write tool call
    assert any(tc.tool_name == "Write" for turn in turns for tc in turn.tool_calls)


def test_deduplication():
    """Duplicate assistant records sharing a requestId must not double-count tokens."""
    from ccspy.parser import parse_file

    _, turns, _ = parse_file(FIXTURES / "fixture_clean.jsonl")
    req_ids = [t.request_id for t in turns]
    assert len(req_ids) == len(set(req_ids)), "Duplicate requestIds found — deduplication broken"


def test_malformed_line_skipped():
    """A malformed JSON line must not crash the parser; subsequent records still parse."""
    from ccspy.parser import parse_file

    session, turns, _ = parse_file(FIXTURES / "fixture_malformed.jsonl", verbose=False)
    assert session is not None
    assert len(turns) == 2  # two valid assistant turns after the bad line


def test_multiday_session():
    """Session turns spanning midnight still parse; started_at < ended_at."""
    from ccspy.parser import parse_file

    session, turns, _ = parse_file(FIXTURES / "fixture_multiday.jsonl")
    assert session is not None
    assert len(turns) == 2
    assert session.started_at < session.ended_at


def test_cache_tokens_parsed():
    """cache_creation and cache_read tokens are correctly extracted from usage."""
    from ccspy.parser import parse_file

    _, turns, _ = parse_file(FIXTURES / "fixture_cache_heavy.jsonl")
    assert len(turns) == 3
    first_turn = turns[0]
    assert first_turn.usage.cache_creation_input_tokens == 52000
    assert first_turn.usage.cache_creation_1h_tokens == 52000
    # Second turn onwards should have cache reads, not writes
    assert turns[1].usage.cache_read_input_tokens > 0


def test_subagent_session_flagged():
    """Sessions with isSidechain=True should be flagged as subagent sessions."""
    from ccspy.parser import parse_file

    session, turns, _ = parse_file(FIXTURES / "fixture_subagent.jsonl")
    assert session is not None
    assert session.is_sidechain is True


def test_first_user_text_captured():
    """The first user message text should be stored on the session."""
    from ccspy.parser import parse_file

    session, _, _ = parse_file(FIXTURES / "fixture_clean.jsonl")
    assert session is not None
    assert "login form" in session.first_user_text.lower()
