"""JSONL transcript parser — streams lines, yields typed records.

Phase 1 findings baked in:
- Two file layouts: old (project/uuid.jsonl) and new (project/uuid/subagents/agent-*.jsonl).
- Each API response emits 2 assistant records sharing the same requestId; deduplicate by
  keeping usage from the first and merging tool_calls from all.
- input_tokens is near-zero; real work lives in cache_creation and cache_read tokens.
- Extra record types (queue-operation, ai-title, progress, etc.) are silently skipped.
- cache_creation sub-fields: ephemeral_1h_input_tokens and ephemeral_5m_input_tokens
  allow differentiated pricing.
"""
from __future__ import annotations

import json
import logging
import sys
from pathlib import Path
from typing import Generator, Iterator

from pydantic import BaseModel, Field, field_validator

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Pydantic records
# ---------------------------------------------------------------------------


class UsageRecord(BaseModel):
    input_tokens: int = 0
    output_tokens: int = 0
    cache_creation_input_tokens: int = 0
    cache_read_input_tokens: int = 0
    cache_creation_1h_tokens: int = 0
    cache_creation_5m_tokens: int = 0

    @property
    def total_tokens(self) -> int:
        return (
            self.input_tokens
            + self.output_tokens
            + self.cache_creation_input_tokens
            + self.cache_read_input_tokens
        )


class ToolCallRecord(BaseModel):
    tool_name: str
    tool_id: str = ""
    success: bool = True


class TurnRecord(BaseModel):
    """One logical assistant turn (deduplicated from potentially multiple JSONL lines)."""

    turn_id: str
    session_id: str
    request_id: str
    ts: str
    model: str
    usage: UsageRecord = Field(default_factory=UsageRecord)
    tool_calls: list[ToolCallRecord] = Field(default_factory=list)
    first_user_text: str = ""
    is_sidechain: bool = False
    user_msg_ts: str = ""


class SessionRecord(BaseModel):
    """Metadata for one session, extracted from its JSONL file."""

    session_id: str
    project_path: str
    project_name: str
    started_at: str = ""
    ended_at: str = ""
    summary: str = ""
    parent_session_id: str = ""
    jsonl_path: str
    is_sidechain: bool = False
    first_user_text: str = ""


# ---------------------------------------------------------------------------
# Path discovery
# ---------------------------------------------------------------------------

from ccspy._paths import CLAUDE_PROJECTS


def discover_jsonl_files(projects_dir: Path = CLAUDE_PROJECTS) -> list[Path]:
    """Return all session JSONL paths under projects_dir.

    Handles both layouts:
      - old: <project>/<uuid>.jsonl
      - new: <project>/<uuid>/subagents/agent-*.jsonl
    """
    found: list[Path] = []
    if not projects_dir.exists():
        return found

    for project_dir in projects_dir.iterdir():
        if not project_dir.is_dir() or project_dir.name == "memory":
            continue
        for item in project_dir.iterdir():
            if item.is_file() and item.suffix == ".jsonl":
                # old layout: project/<uuid>.jsonl
                found.append(item)
            elif item.is_dir():
                # new layout: project/<uuid>/subagents/
                subagents_dir = item / "subagents"
                if subagents_dir.is_dir():
                    for agent_file in subagents_dir.glob("agent-*.jsonl"):
                        found.append(agent_file)

    return found


def project_name_from_dir(project_dir_name: str) -> str:
    """Decode a URL-encoded project directory name to a human-readable project name.

    The directory encoding replaces path separators with dashes, so we reverse
    that to recover the original path and take the final component.
    E.g. '-Users-ryan-code-fdbk' -> 'fdbk'
    """
    decoded = project_dir_name.replace("-", "/").lstrip("/")
    return Path(decoded).name if decoded else project_dir_name


def session_id_from_path(path: Path) -> str:
    """Extract the session UUID from a JSONL path."""
    name = path.stem
    if name.startswith("agent-"):
        # new layout: agent-<hash>  — session id is in the records themselves
        return name
    return name


# ---------------------------------------------------------------------------
# Streaming parser
# ---------------------------------------------------------------------------


def _parse_usage(raw: dict) -> UsageRecord:
    cache_creation = raw.get("cache_creation", {}) or {}
    return UsageRecord(
        input_tokens=raw.get("input_tokens", 0) or 0,
        output_tokens=raw.get("output_tokens", 0) or 0,
        cache_creation_input_tokens=raw.get("cache_creation_input_tokens", 0) or 0,
        cache_read_input_tokens=raw.get("cache_read_input_tokens", 0) or 0,
        cache_creation_1h_tokens=cache_creation.get("ephemeral_1h_input_tokens", 0) or 0,
        cache_creation_5m_tokens=cache_creation.get("ephemeral_5m_input_tokens", 0) or 0,
    )


def _parse_tool_calls(content: list[dict]) -> list[ToolCallRecord]:
    calls = []
    for block in content:
        if block.get("type") == "tool_use":
            calls.append(
                ToolCallRecord(
                    tool_name=block.get("name", "unknown"),
                    tool_id=block.get("id", ""),
                )
            )
    return calls


def iter_turns(
    path: Path,
    start_offset: int = 0,
    verbose: bool = False,
) -> Generator[tuple[TurnRecord | SessionRecord, int], None, None]:
    """Stream turns and session metadata from a JSONL file.

    Yields (record, byte_offset_after_line) pairs.
    Deduplicates assistant records by requestId — usage is taken from the
    first record seen for that requestId; tool_calls are merged across all.
    Skips unrecognised record types silently.

    Args:
        path: Path to the JSONL file.
        start_offset: Resume from this byte offset (for incremental updates).
        verbose: Log skipped/malformed lines to stderr.
    """
    pending_turns: dict[str, TurnRecord] = {}
    first_user_text = ""
    last_user_ts = ""
    session_meta: SessionRecord | None = None

    # New layout: .../projects/<proj-dir>/<uuid>/subagents/agent-*.jsonl
    # Old layout: .../projects/<proj-dir>/<uuid>.jsonl
    if "subagents" in path.parts:
        project_dir = path.parent.parent.parent
    else:
        project_dir = path.parent
    project_name = project_name_from_dir(project_dir.name)
    # Reverse the encoding: leading dash means the path started at /, dashes = slashes
    project_path = "/" + project_dir.name.lstrip("-").replace("-", "/")

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

            if rtype == "user":
                last_user_ts = record.get("timestamp", "")
                msg = record.get("message", {})
                content = msg.get("content", [])
                if isinstance(content, list) and not first_user_text:
                    # IDE context injections arrive as early text blocks starting with
                    # angle brackets (<ide_opened_file>, <ide_selection>, etc.).
                    # The actual user intent is in the last plain text block.
                    plain_texts = [
                        b.get("text", "").strip()
                        for b in content
                        if isinstance(b, dict) and b.get("type") == "text"
                        and not b.get("text", "").strip().startswith("<")
                    ]
                    if plain_texts:
                        first_user_text = plain_texts[-1][:500]
                    else:
                        # Fall back to any text if all blocks are context injections
                        for block in content:
                            if isinstance(block, dict) and block.get("type") == "text":
                                text = block.get("text", "").strip()
                                if text:
                                    first_user_text = text[:500]
                                    break
                elif isinstance(content, str) and not first_user_text:
                    first_user_text = content[:500]

                sid = record.get("sessionId", "")
                if session_meta is None and sid:
                    is_sc = record.get("isSidechain", False)
                    session_meta = SessionRecord(
                        session_id=sid,
                        project_path=project_path,
                        project_name=project_name,
                        started_at=record.get("timestamp", ""),
                        jsonl_path=str(path),
                        is_sidechain=is_sc,
                        first_user_text="",
                    )
                    yield session_meta, new_offset

            elif rtype == "assistant":
                msg = record.get("message", {})
                req_id = record.get("requestId", record.get("uuid", ""))
                sid = record.get("sessionId", "")
                uuid = record.get("uuid", req_id)
                ts = record.get("timestamp", "")
                model = msg.get("model", "unknown")
                usage_raw = msg.get("usage", {}) or {}
                content = msg.get("content", []) or []
                is_sc = record.get("isSidechain", False)

                if req_id in pending_turns:
                    # Merge tool calls from this continuation record
                    pending_turns[req_id].tool_calls.extend(_parse_tool_calls(content))
                else:
                    turn = TurnRecord(
                        turn_id=uuid,
                        session_id=sid,
                        request_id=req_id,
                        ts=ts,
                        model=model,
                        usage=_parse_usage(usage_raw),
                        tool_calls=_parse_tool_calls(content),
                        is_sidechain=is_sc,
                        user_msg_ts=last_user_ts,
                    )
                    pending_turns[req_id] = turn

                yield pending_turns[req_id], new_offset

            elif rtype == "summary":
                sid = record.get("sessionId", "")
                summary_text = ""
                msg = record.get("summary", record.get("message", ""))
                if isinstance(msg, str):
                    summary_text = msg
                elif isinstance(msg, dict):
                    summary_text = str(msg)
                if session_meta and session_meta.session_id == sid:
                    session_meta.summary = summary_text[:1000]
                yield SessionRecord(
                    session_id=sid,
                    project_path=project_path,
                    project_name=project_name,
                    started_at="",
                    summary=summary_text[:1000],
                    jsonl_path=str(path),
                ), new_offset

            # All other types (queue-operation, ai-title, progress, etc.) skipped silently.

            byte_offset = new_offset

    # Attach first_user_text to session metadata
    if session_meta is not None:
        session_meta.first_user_text = first_user_text
        session_meta.ended_at = ""


def parse_file(path: Path, start_offset: int = 0, verbose: bool = False) -> tuple[
    SessionRecord | None,
    list[TurnRecord],
    int,
]:
    """Parse a full JSONL file and return (session, turns, final_byte_offset).

    Convenience wrapper around iter_turns for non-streaming callers.
    """
    session: SessionRecord | None = None
    turns: list[TurnRecord] = []
    final_offset = start_offset
    seen_request_ids: set[str] = set()
    turns_by_req: dict[str, TurnRecord] = {}

    for record, offset in iter_turns(path, start_offset=start_offset, verbose=verbose):
        final_offset = offset
        if isinstance(record, SessionRecord) and record.started_at:
            session = record
        elif isinstance(record, TurnRecord):
            if record.request_id not in seen_request_ids:
                seen_request_ids.add(record.request_id)
                turns_by_req[record.request_id] = record
            else:
                # Merge additional tool_calls from duplicate records
                turns_by_req[record.request_id].tool_calls = record.tool_calls

    turns = list(turns_by_req.values())
    if session:
        if turns:
            session.started_at = turns[0].ts
            session.ended_at = turns[-1].ts
        session.first_user_text = session.first_user_text or ""

    return session, turns, final_offset
