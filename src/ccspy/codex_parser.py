"""Codex CLI JSONL parser — streams rollout files, yields typed records.

Layout: ~/.codex/sessions/YYYY/MM/DD/rollout-<timestamp>-<uuid>.jsonl
Configurable via CODEX_HOME env var.

Each rollout file is one task (possibly with sub-turns). Key record types:
  session_meta  — first line, session ID + cwd
  turn_context  — per-turn model name + turn_id
  event_msg     — subtypes: task_started, user_message, token_count, task_complete
  response_item — content blocks (skipped for aggregation purposes)

Token data lives in event_msg/token_count → payload.info.last_token_usage
which gives per-turn counts directly (no delta needed).
"""
from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Generator

from ccspy.parser import SessionRecord, ToolCallRecord, TurnRecord, UsageRecord

log = logging.getLogger(__name__)

CODEX_HOME = Path(os.environ["CODEX_HOME"]) if "CODEX_HOME" in os.environ else Path.home() / ".codex"
CODEX_SESSIONS = CODEX_HOME / "sessions"


def discover_codex_jsonl_files() -> list[Path]:
    """Return all rollout JSONL paths under ~/.codex/sessions/."""
    found: list[Path] = []
    if not CODEX_SESSIONS.exists():
        return found
    for f in CODEX_SESSIONS.rglob("rollout-*.jsonl"):
        found.append(f)
    return found


def iter_codex_turns(
    path: Path,
    start_offset: int = 0,
    verbose: bool = False,
) -> Generator[tuple[TurnRecord | SessionRecord, int], None, None]:
    """Stream turns and session metadata from a Codex rollout JSONL file.

    Yields (record, byte_offset_after_line) pairs.
    Accumulates state across lines; emits a TurnRecord on task_complete.
    """
    session_meta: SessionRecord | None = None
    first_user_text = ""

    # Pending turn state
    turn_id: str = ""
    turn_model: str = "unknown"
    turn_ts: str = ""
    turn_usage: UsageRecord = UsageRecord()
    turn_tool_calls: list[ToolCallRecord] = []
    user_msg_ts: str = ""
    pending_user_text: str = ""
    in_turn = False

    with path.open("rb") as fh:
        fh.seek(start_offset)
        byte_offset = start_offset

        for raw_line in fh:
            new_offset = byte_offset + len(raw_line)
            line = raw_line.decode("utf-8", errors="replace").strip()

            if not line:
                byte_offset = new_offset
                continue

            try:
                record = json.loads(line)
            except json.JSONDecodeError as exc:
                if verbose:
                    log.warning("Skipping malformed JSON in %s at offset %d: %s", path, byte_offset, exc)
                byte_offset = new_offset
                continue

            rtype = record.get("type", "")
            ts = record.get("timestamp", "")

            if rtype == "session_meta":
                payload = record.get("payload", {})
                sid = payload.get("id", "")
                cwd = payload.get("cwd", "")
                project_name = Path(cwd).name if cwd else path.stem
                session_meta = SessionRecord(
                    session_id=sid,
                    project_path=cwd,
                    project_name=project_name,
                    started_at=payload.get("timestamp", ts),
                    jsonl_path=str(path),
                    is_sidechain=False,
                    first_user_text="",
                )
                yield session_meta, new_offset

            elif rtype == "turn_context":
                payload = record.get("payload", {})
                turn_model = payload.get("model", "unknown")
                if not turn_id:
                    turn_id = payload.get("turn_id", "")

            elif rtype == "event_msg":
                payload = record.get("payload", {})
                ptype = payload.get("type", "")

                if ptype == "task_started":
                    turn_id = payload.get("turn_id", "")
                    in_turn = True
                    turn_tool_calls = []
                    turn_usage = UsageRecord()
                    turn_ts = ts
                    pending_user_text = ""
                    user_msg_ts = ""

                elif ptype == "user_message":
                    user_msg_ts = ts
                    msg_text = payload.get("message", "").strip()
                    if msg_text and not first_user_text:
                        first_user_text = msg_text[:500]
                    if msg_text and not pending_user_text:
                        pending_user_text = msg_text[:500]

                elif ptype == "token_count":
                    info = payload.get("info", {})
                    usage = info.get("last_token_usage", {})
                    turn_usage = UsageRecord(
                        input_tokens=usage.get("input_tokens", 0) or 0,
                        output_tokens=(usage.get("output_tokens", 0) or 0)
                            + (usage.get("reasoning_output_tokens", 0) or 0),
                        cache_creation_input_tokens=0,
                        cache_read_input_tokens=usage.get("cached_input_tokens", 0) or 0,
                    )
                    turn_ts = ts

                elif ptype == "task_complete" and in_turn and turn_id:
                    sid = session_meta.session_id if session_meta else path.stem
                    turn = TurnRecord(
                        turn_id=turn_id,
                        session_id=sid,
                        request_id=turn_id,
                        ts=turn_ts or ts,
                        model=turn_model,
                        usage=turn_usage,
                        tool_calls=turn_tool_calls,
                        is_sidechain=False,
                        user_msg_ts=user_msg_ts,
                        first_user_text=pending_user_text,
                    )
                    yield turn, new_offset
                    in_turn = False
                    turn_id = ""

            byte_offset = new_offset

    if session_meta is not None:
        session_meta.first_user_text = first_user_text
