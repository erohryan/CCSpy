"""Opt-in community leaderboard — peak daily tokens metric."""
from __future__ import annotations

import json
import time
from datetime import datetime, timezone

from ccspy._paths import CONFIG_DIR
from ccspy import _supabase as sb
from ccspy import identity

_TABLE    = "leaderboard"
_CACHE    = CONFIG_DIR / "lb_cache.json"
_SYNC_TTL = 120  # seconds between live API calls


# ── Leaderboard opt-in state ──────────────────────────────────────────────────

def is_opted_in() -> bool:
    return bool(identity.read_section("leaderboard").get("opted_in", False))


def opt_in() -> None:
    """Enable leaderboard participation for the current identity."""
    identity.update_section("leaderboard", {"opted_in": True})


def opt_out() -> None:
    identity.update_section("leaderboard", {"opted_in": False})


# ── Local stats ───────────────────────────────────────────────────────────────

def peak_day_info(store) -> tuple[int, str | None]:
    """All-time peak tokens for a single calendar day, plus the date it occurred."""
    rows = store.query(
        """
        SELECT date(s.started_at, 'localtime') AS day,
               SUM(t.input_tokens + t.output_tokens +
                   t.cache_creation_tokens + t.cache_read_tokens) AS tok
        FROM sessions s
        JOIN turns t ON s.session_id = t.session_id
        GROUP BY day
        ORDER BY tok DESC
        LIMIT 1
        """,
        (),
    )
    if rows:
        return int(rows[0]["tok"] or 0), rows[0]["day"]
    return 0, None


def peak_day_tokens(store) -> int:
    """All-time peak tokens consumed in a single calendar day."""
    return peak_day_info(store)[0]


def today_tokens(store) -> int:
    """Tokens consumed today (local calendar day)."""
    rows = store.query(
        """
        SELECT COALESCE(SUM(t.input_tokens + t.output_tokens +
                            t.cache_creation_tokens + t.cache_read_tokens), 0) AS tok
        FROM sessions s
        JOIN turns t ON s.session_id = t.session_id
        WHERE date(s.started_at, 'localtime') = date('now', 'localtime')
        """,
        (),
    )
    return int(rows[0]["tok"] or 0) if rows else 0


# ── Public API ────────────────────────────────────────────────────────────────

def fetch_top(limit: int = 10) -> list[dict]:
    """Fetch the top-N leaderboard entries sorted by peak_day descending."""
    result = sb.get(
        f"{_TABLE}?select=pseudonym,peak_day,peak_day_date"
        f"&order=peak_day.desc&limit={limit}"
    )
    return result if isinstance(result, list) else []


def fetch_rank(token: str, my_peak: int) -> int | None:
    """Return 1-based rank for this token, or None on network error."""
    above = sb.get(
        f"{_TABLE}?select=user_token&peak_day=gt.{my_peak}"
    )
    if above is None:
        return None
    return len(above) + 1


def push_score(store) -> bool:
    """Submit or update the current user's peak-day score."""
    token     = identity.get_user_token()
    pseudonym = identity.get_pseudonym()
    if not token or not pseudonym:
        return False
    peak, peak_date = peak_day_info(store)
    if peak == 0:
        return False
    return sb.upsert(_TABLE, {
        "user_token":    token,
        "pseudonym":     pseudonym,
        "peak_day":      peak,
        "peak_day_date": peak_date,
        "updated_at":    datetime.now(timezone.utc).isoformat(),
    })


# ── Cache ─────────────────────────────────────────────────────────────────────

def load_cache() -> dict:
    if _CACHE.exists():
        try:
            d = json.loads(_CACHE.read_text())
            if time.time() - d.get("ts", 0) < _SYNC_TTL:
                return d
        except Exception:
            pass
    return {}


def save_cache(
    top: list,
    rank: int | None,
    peak: int,
    peak_date: str | None = None,
    today: int = 0,
) -> None:
    _CACHE.parent.mkdir(parents=True, exist_ok=True)
    _CACHE.write_text(json.dumps({
        "top": top, "rank": rank, "peak": peak,
        "peak_date": peak_date, "today": today,
        "ts": time.time(),
    }))
