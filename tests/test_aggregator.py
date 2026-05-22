"""Tests for aggregator.py — stub, fully implemented in Phase 4."""
import pytest


@pytest.fixture
def populated_store(tmp_path):
    """Create an in-memory store populated from all fixtures."""
    from ccspy.store import Store
    import sqlite3

    db_path = tmp_path / "test.db"
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    store = Store(conn)
    # executescript to create tables
    conn.executescript(
        """
        PRAGMA journal_mode=WAL;
        PRAGMA foreign_keys=ON;
        CREATE TABLE IF NOT EXISTS files (path TEXT PRIMARY KEY, mtime REAL NOT NULL, last_byte_offset INTEGER NOT NULL DEFAULT 0);
        CREATE TABLE IF NOT EXISTS sessions (session_id TEXT PRIMARY KEY, project_path TEXT NOT NULL, project_name TEXT NOT NULL, started_at TEXT NOT NULL DEFAULT '', ended_at TEXT NOT NULL DEFAULT '', summary TEXT NOT NULL DEFAULT '', parent_session_id TEXT NOT NULL DEFAULT '', jsonl_path TEXT NOT NULL, is_sidechain INTEGER NOT NULL DEFAULT 0, first_user_text TEXT NOT NULL DEFAULT '');
        CREATE TABLE IF NOT EXISTS turns (turn_id TEXT PRIMARY KEY, session_id TEXT NOT NULL, ts TEXT NOT NULL, model TEXT NOT NULL, input_tokens INTEGER NOT NULL DEFAULT 0, output_tokens INTEGER NOT NULL DEFAULT 0, cache_creation_tokens INTEGER NOT NULL DEFAULT 0, cache_read_tokens INTEGER NOT NULL DEFAULT 0, cache_creation_1h_tokens INTEGER NOT NULL DEFAULT 0, cache_creation_5m_tokens INTEGER NOT NULL DEFAULT 0, user_msg_ts TEXT NOT NULL DEFAULT '', first_user_text TEXT NOT NULL DEFAULT '');
        CREATE TABLE IF NOT EXISTS tool_calls (id INTEGER PRIMARY KEY AUTOINCREMENT, turn_id TEXT NOT NULL, tool_name TEXT NOT NULL, success INTEGER NOT NULL DEFAULT 1);
        """
    )
    conn.commit()

    from pathlib import Path
    fixtures = Path(__file__).parent / "fixtures"
    from ccspy.parser import parse_file

    for f in fixtures.glob("*.jsonl"):
        session, turns, _ = parse_file(f)
        with conn:
            if session:
                conn.execute(
                    "INSERT OR REPLACE INTO sessions VALUES (?,?,?,?,?,?,?,?,?,?)",
                    (session.session_id, session.project_path, session.project_name,
                     session.started_at, session.ended_at, session.summary,
                     session.parent_session_id, str(f), int(session.is_sidechain),
                     session.first_user_text),
                )
            for t in turns:
                sid = session.session_id if session else t.session_id
                conn.execute(
                    "INSERT OR REPLACE INTO turns VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                    (t.turn_id, sid, t.ts, t.model, t.usage.input_tokens,
                     t.usage.output_tokens, t.usage.cache_creation_input_tokens,
                     t.usage.cache_read_input_tokens, t.usage.cache_creation_1h_tokens,
                     t.usage.cache_creation_5m_tokens, t.user_msg_ts, t.first_user_text),
                )
                for tc in t.tool_calls:
                    conn.execute(
                        "INSERT INTO tool_calls(turn_id, tool_name, success) VALUES (?,?,?)",
                        (t.turn_id, tc.tool_name, 1),
                    )
    return store


def test_totals_non_zero(populated_store):
    from ccspy.aggregator import Aggregator
    agg = Aggregator(populated_store)
    data = agg.build(days=365)
    assert data.totals.total_tokens > 0


def test_by_project_sorted_descending(populated_store):
    from ccspy.aggregator import Aggregator
    agg = Aggregator(populated_store)
    data = agg.build(days=365)
    totals = [p.total_tokens for p in data.by_project]
    assert totals == sorted(totals, reverse=True)


def test_by_model_pct_sums_to_100(populated_store):
    from ccspy.aggregator import Aggregator
    agg = Aggregator(populated_store)
    data = agg.build(days=365)
    total_pct = sum(m.pct for m in data.by_model)
    assert abs(total_pct - 100.0) < 1.0  # allow rounding tolerance


def test_export_csv_has_required_columns(populated_store):
    from ccspy.aggregator import Aggregator
    agg = Aggregator(populated_store)
    csv_text = agg.export(days=365, fmt="csv")
    header = csv_text.splitlines()[0]
    for col in ["date", "project", "model", "input_tokens", "output_tokens"]:
        assert col in header


def test_by_hour_has_24_buckets(populated_store):
    from ccspy.aggregator import Aggregator
    agg = Aggregator(populated_store)
    data = agg.build(days=365)
    assert len(data.by_hour) == 24
