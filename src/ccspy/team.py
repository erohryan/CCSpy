"""Team management backend for ccspy."""
from __future__ import annotations

import random
from datetime import datetime, timezone, timedelta
from collections import defaultdict

from ccspy import _supabase as sb
from ccspy import identity

# ── Word lists ────────────────────────────────────────────────────────────────

_ADJECTIVES = [
    "swift", "brave", "calm", "dark", "eager",
    "fierce", "gentle", "happy", "idle", "jolly",
    "keen", "lively", "merry", "noble", "odd",
    "proud", "quiet", "rapid", "sharp", "tall",
    "ultra", "vivid", "warm", "xenial", "young",
    "zesty", "amber", "crisp", "dusty", "frosty",
]

_PLURAL_ANIMALS = [
    "wolves", "hawks", "bears", "deer", "crows",
    "lynxes", "moles", "newts", "orcas", "pumas",
    "quails", "rooks", "seals", "toads", "voles",
    "wasps", "yaks", "bisons", "cranes", "dingoes",
    "eagles", "finches", "goats", "herons", "ibises",
    "jackals", "kites", "lemurs", "moose", "cobras",
]


# ── Name generation ───────────────────────────────────────────────────────────

def generate_team_name() -> str:
    """Return a random team name like 'swift_wolves'."""
    adj    = random.choice(_ADJECTIVES)
    animal = random.choice(_PLURAL_ANIMALS)
    return f"{adj}_{animal}"


# ── Team config accessors ─────────────────────────────────────────────────────

def get_team_config() -> dict:
    return identity.read_section("team")


def is_in_team() -> bool:
    return bool(get_team_config().get("team_id", ""))


def get_team_id() -> str:
    return get_team_config().get("team_id", "")


def get_team_name() -> str:
    return get_team_config().get("team_name", "")


def get_role() -> str:
    return get_team_config().get("role", "member")


# ── Team operations ───────────────────────────────────────────────────────────

def create_team() -> tuple[str, str] | None:
    """Create a new team with a generated name.

    Retries up to 5 times on name collision (UNIQUE constraint on teams.name).
    Adds self as admin in team_members.
    Writes [team] to user.toml.

    Returns (team_id, name) on success, None on failure.
    """
    token     = identity.get_user_token()
    pseudonym = identity.get_pseudonym()
    if not token:
        return None

    for _ in range(5):
        name   = generate_team_name()
        result = sb.post("teams", {"name": name}, returning=True)
        if not result:
            # Likely a name collision or error — retry
            continue
        if isinstance(result, list) and len(result) > 0:
            row     = result[0]
            team_id = row.get("team_id", "")
        elif isinstance(result, dict):
            team_id = result.get("team_id", "")
        else:
            continue

        if not team_id:
            continue

        # Add self as admin in team_members
        ok = sb.post("team_members", {
            "user_token": token,
            "team_id":    team_id,
            "role":       "admin",
            "pseudonym":  pseudonym,
        })
        if ok is None:
            # team_members insert failed — still keep going
            pass

        identity.update_section("team", {
            "team_id":   team_id,
            "team_name": name,
            "role":      "admin",
        })
        return (team_id, name)

    return None


def join_team(name: str) -> bool:
    """Look up team by name and join it as a member.

    Returns True on success.
    """
    token     = identity.get_user_token()
    pseudonym = identity.get_pseudonym()
    if not token:
        return False

    result = sb.get(
        f"teams?name=eq.{name}&select=team_id,name&limit=1"
    )
    if not result or not isinstance(result, list) or len(result) == 0:
        return False

    row     = result[0]
    team_id = row.get("team_id", "")
    if not team_id:
        return False

    ok = sb.post("team_members", {
        "user_token": token,
        "team_id":    team_id,
        "role":       "member",
        "pseudonym":  pseudonym,
    })
    if ok is None:
        return False

    identity.update_section("team", {
        "team_id":   team_id,
        "team_name": name,
        "role":      "member",
    })
    return True


def leave_team() -> bool:
    """Delete self from team_members and clear the [team] section."""
    token   = identity.get_user_token()
    team_id = get_team_id()
    if not token or not team_id:
        return False

    ok = sb.delete(
        f"team_members?user_token=eq.{token}&team_id=eq.{team_id}"
    )
    # Clear local config regardless of API result
    identity.update_section("team", {
        "team_id":   "",
        "team_name": "",
        "role":      "",
    })
    return ok


def fetch_members(team_id: str) -> list[dict]:
    """Return all rows from team_members for the given team."""
    result = sb.get(
        f"team_members?team_id=eq.{team_id}"
        "&select=user_token,pseudonym,role,joined_at"
    )
    return result if isinstance(result, list) else []


def fetch_stats(team_id: str, days: int = 7) -> list[dict]:
    """Return team_stats rows for the last *days* days."""
    since = (datetime.now(timezone.utc) - timedelta(days=days)).date().isoformat()
    result = sb.get(
        f"team_stats?team_id=eq.{team_id}&day=gte.{since}"
        "&select=user_token,day,tokens_input,tokens_output,tokens_cache,"
        "prompt_count,favourite_model"
    )
    return result if isinstance(result, list) else []


def push_stats(store, days: int = 7) -> None:
    """Push last *days* days of local stats to team_stats.

    Queries SQLite for daily token totals and per-model token breakdown,
    then upserts one row per (user_token, team_id, day).
    """
    token   = identity.get_user_token()
    team_id = get_team_id()
    if not token or not team_id:
        return

    # 1. Daily totals
    daily_rows = store.query(
        """
        SELECT
            date(s.started_at, 'localtime') AS day,
            COALESCE(SUM(t.input_tokens), 0)            AS tokens_input,
            COALESCE(SUM(t.output_tokens), 0)           AS tokens_output,
            COALESCE(SUM(t.cache_creation_tokens
                        + t.cache_read_tokens), 0)       AS tokens_cache,
            COUNT(t.turn_id)                             AS prompt_count
        FROM sessions s
        JOIN turns t ON s.session_id = t.session_id
        WHERE date(s.started_at, 'localtime') >= date('now', :neg_days)
        GROUP BY day
        """,
        {"neg_days": f"-{days} days"},
    )

    # 2. Model breakdown per day — top model per day
    model_rows = store.query(
        """
        SELECT
            date(s.started_at, 'localtime') AS day,
            t.model,
            COALESCE(SUM(t.input_tokens + t.output_tokens
                        + t.cache_creation_tokens
                        + t.cache_read_tokens), 0) AS tok
        FROM sessions s
        JOIN turns t ON s.session_id = t.session_id
        WHERE date(s.started_at, 'localtime') >= date('now', :neg_days)
          AND t.model IS NOT NULL
        GROUP BY day, t.model
        ORDER BY tok DESC
        """,
        {"neg_days": f"-{days} days"},
    )

    # Pick favourite model per day in Python (first model seen per day is top)
    fav_model: dict[str, str] = {}
    for row in (model_rows or []):
        day = row.get("day", "")
        if day and day not in fav_model:
            fav_model[day] = row.get("model", "") or ""

    now_iso = datetime.now(timezone.utc).isoformat()
    for row in (daily_rows or []):
        day = row.get("day", "")
        if not day:
            continue
        sb.upsert("team_stats", {
            "user_token":      token,
            "team_id":         team_id,
            "day":             day,
            "tokens_input":    int(row.get("tokens_input",  0) or 0),
            "tokens_output":   int(row.get("tokens_output", 0) or 0),
            "tokens_cache":    int(row.get("tokens_cache",  0) or 0),
            "prompt_count":    int(row.get("prompt_count",  0) or 0),
            "favourite_model": fav_model.get(day, ""),
            "updated_at":      now_iso,
        })
