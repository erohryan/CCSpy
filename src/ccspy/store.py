"""SQLite cache of parsed session and turn data.

Schema:
  sessions  — one row per JSONL file (session-level metadata)
  turns     — one row per deduplicated assistant turn
  tool_calls — one row per tool call within a turn

The store tracks mtime + byte_offset per file for incremental parsing.
"""
from __future__ import annotations

import logging
import sqlite3
import sys
from pathlib import Path
from typing import Any

from ccspy.parser import (
    SessionRecord,
    TurnRecord,
    discover_jsonl_files,
    parse_file,
)
from ccspy.codex_parser import (
    discover_codex_jsonl_files,
    iter_codex_turns,
)

log = logging.getLogger(__name__)

CONFIG_DIR = Path.home() / ".config" / "ccspy"
_DB_NAME = "cache.db"

_DDL = """
PRAGMA journal_mode=WAL;
PRAGMA foreign_keys=ON;

CREATE TABLE IF NOT EXISTS files (
    path            TEXT PRIMARY KEY,
    mtime           REAL NOT NULL,
    last_byte_offset INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS sessions (
    session_id          TEXT PRIMARY KEY,
    project_path        TEXT NOT NULL,
    project_name        TEXT NOT NULL,
    started_at          TEXT NOT NULL DEFAULT '',
    ended_at            TEXT NOT NULL DEFAULT '',
    summary             TEXT NOT NULL DEFAULT '',
    parent_session_id   TEXT NOT NULL DEFAULT '',
    jsonl_path          TEXT NOT NULL,
    is_sidechain        INTEGER NOT NULL DEFAULT 0,
    first_user_text     TEXT NOT NULL DEFAULT '',
    source              TEXT NOT NULL DEFAULT 'claude'
);

CREATE TABLE IF NOT EXISTS turns (
    turn_id                     TEXT PRIMARY KEY,
    session_id                  TEXT NOT NULL REFERENCES sessions(session_id) ON DELETE CASCADE,
    ts                          TEXT NOT NULL,
    model                       TEXT NOT NULL,
    input_tokens                INTEGER NOT NULL DEFAULT 0,
    output_tokens               INTEGER NOT NULL DEFAULT 0,
    cache_creation_tokens       INTEGER NOT NULL DEFAULT 0,
    cache_read_tokens           INTEGER NOT NULL DEFAULT 0,
    cache_creation_1h_tokens    INTEGER NOT NULL DEFAULT 0,
    cache_creation_5m_tokens    INTEGER NOT NULL DEFAULT 0,
    user_msg_ts                 TEXT NOT NULL DEFAULT '',
    first_user_text             TEXT NOT NULL DEFAULT '',
    source                      TEXT NOT NULL DEFAULT 'claude'
);

CREATE TABLE IF NOT EXISTS tool_calls (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    turn_id     TEXT NOT NULL REFERENCES turns(turn_id) ON DELETE CASCADE,
    tool_name   TEXT NOT NULL,
    success     INTEGER NOT NULL DEFAULT 1
);

CREATE INDEX IF NOT EXISTS idx_turns_session ON turns(session_id);
CREATE INDEX IF NOT EXISTS idx_turns_ts ON turns(ts);
CREATE INDEX IF NOT EXISTS idx_tool_calls_turn ON tool_calls(turn_id);
"""


class Store:
    """Manages the SQLite cache. Pass the instance into UI and aggregator."""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    # ------------------------------------------------------------------
    # Factory / lifecycle
    # ------------------------------------------------------------------

    @classmethod
    def db_path(cls) -> Path:
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        return CONFIG_DIR / _DB_NAME

    @classmethod
    def open(cls) -> "Store":
        path = cls.db_path()
        conn = sqlite3.connect(str(path), check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.executescript(_DDL)
        for migration in [
            "ALTER TABLE turns ADD COLUMN user_msg_ts TEXT NOT NULL DEFAULT ''",
            "ALTER TABLE turns ADD COLUMN source TEXT NOT NULL DEFAULT 'claude'",
            "ALTER TABLE sessions ADD COLUMN source TEXT NOT NULL DEFAULT 'claude'",
        ]:
            try:
                conn.execute(migration)
            except sqlite3.OperationalError:
                pass  # column already exists
        conn.commit()
        return cls(conn)

    def close(self) -> None:
        self._conn.close()

    # ------------------------------------------------------------------
    # Sync
    # ------------------------------------------------------------------

    def sync(self, force: bool = False, verbose: bool = False) -> None:
        """Scan Claude and Codex session dirs and update the cache for changed files."""
        for path in discover_jsonl_files():
            try:
                self._sync_file(path, source="claude", force=force, verbose=verbose)
            except Exception as exc:
                log.warning("Failed to sync %s: %s", path, exc)
        for path in discover_codex_jsonl_files():
            try:
                self._sync_codex_file(path, force=force, verbose=verbose)
            except Exception as exc:
                log.warning("Failed to sync codex %s: %s", path, exc)

    def _sync_file(self, path: Path, source: str, force: bool, verbose: bool) -> None:
        mtime = path.stat().st_mtime
        row = self._conn.execute(
            "SELECT mtime, last_byte_offset FROM files WHERE path = ?", (str(path),)
        ).fetchone()

        if not force and row and abs(row["mtime"] - mtime) < 0.001:
            return  # up to date

        start_offset = 0 if force else (row["last_byte_offset"] if row else 0)

        session, turns, final_offset = parse_file(path, start_offset=start_offset, verbose=verbose)

        with self._conn:
            if session:
                self._upsert_session(session, source=source)
            for turn in turns:
                sid = session.session_id if session else turn.session_id
                self._upsert_turn(turn, sid, source=source)

            self._conn.execute(
                "INSERT OR REPLACE INTO files(path, mtime, last_byte_offset) VALUES (?, ?, ?)",
                (str(path), mtime, final_offset),
            )

    def _sync_codex_file(self, path: Path, force: bool, verbose: bool) -> None:
        mtime = path.stat().st_mtime
        row = self._conn.execute(
            "SELECT mtime, last_byte_offset FROM files WHERE path = ?", (str(path),)
        ).fetchone()

        if not force and row and abs(row["mtime"] - mtime) < 0.001:
            return

        start_offset = 0 if force else (row["last_byte_offset"] if row else 0)

        session: SessionRecord | None = None
        final_offset = start_offset

        with self._conn:
            for record, offset in iter_codex_turns(path, start_offset=start_offset, verbose=verbose):
                final_offset = offset
                if isinstance(record, SessionRecord):
                    session = record
                    self._upsert_session(session, source="codex")
                elif isinstance(record, TurnRecord) and session:
                    self._upsert_turn(record, session.session_id, source="codex")

            self._conn.execute(
                "INSERT OR REPLACE INTO files(path, mtime, last_byte_offset) VALUES (?, ?, ?)",
                (str(path), mtime, final_offset),
            )

    def _upsert_session(self, s: SessionRecord, source: str = "claude") -> None:
        self._conn.execute(
            """INSERT INTO sessions
               (session_id, project_path, project_name, started_at, ended_at, summary,
                parent_session_id, jsonl_path, is_sidechain, first_user_text, source)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(session_id) DO UPDATE SET
                 ended_at = excluded.ended_at,
                 summary  = excluded.summary,
                 first_user_text = excluded.first_user_text
            """,
            (
                s.session_id, s.project_path, s.project_name,
                s.started_at, s.ended_at, s.summary,
                s.parent_session_id, s.jsonl_path,
                int(s.is_sidechain), s.first_user_text, source,
            ),
        )

    def _upsert_turn(self, t: TurnRecord, session_id: str, source: str = "claude") -> None:
        self._conn.execute(
            """INSERT INTO turns
               (turn_id, session_id, ts, model,
                input_tokens, output_tokens, cache_creation_tokens, cache_read_tokens,
                cache_creation_1h_tokens, cache_creation_5m_tokens, user_msg_ts, source)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(turn_id) DO UPDATE SET
                 ts = excluded.ts,
                 model = excluded.model,
                 input_tokens = excluded.input_tokens,
                 output_tokens = excluded.output_tokens,
                 cache_creation_tokens = excluded.cache_creation_tokens,
                 cache_read_tokens = excluded.cache_read_tokens,
                 cache_creation_1h_tokens = excluded.cache_creation_1h_tokens,
                 cache_creation_5m_tokens = excluded.cache_creation_5m_tokens,
                 user_msg_ts = excluded.user_msg_ts
            """,
            (
                t.turn_id, session_id, t.ts, t.model,
                t.usage.input_tokens, t.usage.output_tokens,
                t.usage.cache_creation_input_tokens, t.usage.cache_read_input_tokens,
                t.usage.cache_creation_1h_tokens, t.usage.cache_creation_5m_tokens,
                t.user_msg_ts, source,
            ),
        )
        self._conn.execute("DELETE FROM tool_calls WHERE turn_id = ?", (t.turn_id,))
        for tc in t.tool_calls:
            self._conn.execute(
                "INSERT INTO tool_calls(turn_id, tool_name, success) VALUES (?, ?, ?)",
                (t.turn_id, tc.tool_name, int(tc.success)),
            )

    # ------------------------------------------------------------------
    # Query helpers (used by Aggregator)
    # ------------------------------------------------------------------

    def query(self, sql: str, params: tuple = ()) -> list[sqlite3.Row]:
        return self._conn.execute(sql, params).fetchall()

    def execute(self, sql: str, params: tuple = ()) -> sqlite3.Cursor:
        return self._conn.execute(sql, params)
