"""Live session detection via mtime polling.

A session is "live" if its JSONL file's mtime is within the last 5 minutes.
Checked every 5 seconds via a Textual timer (no watchdog dependency).
"""
from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path

from ccspy.parser import discover_jsonl_files

LIVE_THRESHOLD_SECONDS = 300  # 5 minutes
MAX_LIVE_SHOWN = 4


@dataclass
class LiveSession:
    session_id: str
    project_name: str
    jsonl_path: Path
    model: str
    total_tokens: int
    recent_token_counts: list[int]  # last 6 turns, for sparkline
    started_at: str
    age_seconds: float


def get_live_sessions(store) -> list[LiveSession]:
    """Return up to MAX_LIVE_SHOWN live sessions, sorted by most-recently active."""
    now = time.time()
    candidates = []

    for path in discover_jsonl_files():
        try:
            mtime = path.stat().st_mtime
        except OSError:
            continue
        age = now - mtime
        if age > LIVE_THRESHOLD_SECONDS:
            continue
        candidates.append((age, path))

    candidates.sort(key=lambda x: x[0])
    live: list[LiveSession] = []

    for age, path in candidates[:MAX_LIVE_SHOWN]:
        session = _build_live_session(path, age, store)
        if session:
            live.append(session)

    return live


def _build_live_session(path: Path, age_seconds: float, store) -> LiveSession | None:
    """Query the store for metadata about a live session."""
    project_dir = path.parent.parent if "subagents" in str(path) else path.parent
    from ccspy.parser import project_name_from_dir
    project_name = project_name_from_dir(project_dir.name)

    rows = store.query(
        """
        SELECT t.model, t.turn_id,
          (t.input_tokens + t.output_tokens + t.cache_creation_tokens + t.cache_read_tokens) as total,
          s.session_id, s.started_at
        FROM turns t
        JOIN sessions s ON t.session_id = s.session_id
        WHERE s.jsonl_path = ?
        ORDER BY t.ts DESC
        LIMIT 6
        """,
        (str(path),),
    )
    if not rows:
        return None

    model = rows[0]["model"]
    session_id = rows[0]["session_id"]
    started_at = rows[0]["started_at"]
    recent = [r["total"] or 0 for r in rows]
    recent.reverse()

    total_row = store.query(
        """
        SELECT SUM(input_tokens + output_tokens + cache_creation_tokens + cache_read_tokens) as t
        FROM turns WHERE session_id = ?
        """,
        (session_id,),
    )
    total_tokens = (total_row[0]["t"] or 0) if total_row else 0

    return LiveSession(
        session_id=session_id,
        project_name=project_name,
        jsonl_path=path,
        model=model,
        total_tokens=total_tokens,
        recent_token_counts=recent,
        started_at=started_at,
        age_seconds=age_seconds,
    )
