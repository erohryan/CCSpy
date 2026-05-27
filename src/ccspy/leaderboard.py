"""Opt-in community leaderboard — peak daily tokens metric.

Supabase one-time setup (run in your project's SQL editor at supabase.com):

    CREATE TABLE leaderboard (
      user_token  uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
      pseudonym   text        NOT NULL,
      peak_day    bigint      NOT NULL DEFAULT 0,
      updated_at  timestamptz NOT NULL DEFAULT now()
    );
    ALTER TABLE leaderboard ENABLE ROW LEVEL SECURITY;
    CREATE POLICY "public read"   ON leaderboard FOR SELECT USING (true);
    CREATE POLICY "anyone insert" ON leaderboard FOR INSERT WITH CHECK (true);
    CREATE POLICY "owner update"  ON leaderboard FOR UPDATE USING (true) WITH CHECK (true);
    CREATE INDEX ON leaderboard (peak_day DESC);

Then fill in SUPABASE_URL and SUPABASE_ANON_KEY below.
"""
from __future__ import annotations

import json
import time
import uuid
import urllib.request
import urllib.error
from datetime import datetime, timezone
from pathlib import Path

from ccspy._paths import CONFIG_DIR

# ── Supabase project credentials (anon key is safe to ship) ──────────────────
SUPABASE_URL      = "https://YOUR-PROJECT.supabase.co"
SUPABASE_ANON_KEY = "YOUR-ANON-KEY"
# ─────────────────────────────────────────────────────────────────────────────

_TABLE    = "leaderboard"
_USER_CFG = CONFIG_DIR / "user.toml"
_CACHE    = CONFIG_DIR / "lb_cache.json"
_SYNC_TTL = 120  # seconds between live API calls


# ── Config I/O ────────────────────────────────────────────────────────────────

def _read_cfg() -> dict:
    if not _USER_CFG.exists():
        return {}
    try:
        import tomllib
    except ImportError:
        try:
            import tomli as tomllib  # type: ignore
        except ImportError:
            return {}
    with _USER_CFG.open("rb") as f:
        try:
            return tomllib.load(f)
        except Exception:
            return {}


def _write_cfg(data: dict) -> None:
    _USER_CFG.parent.mkdir(parents=True, exist_ok=True)
    lines: list[str] = []
    for section, values in data.items():
        lines.append(f"[{section}]")
        for k, v in values.items():
            if isinstance(v, bool):
                lines.append(f"{k} = {'true' if v else 'false'}")
            elif isinstance(v, str):
                escaped = v.replace("\\", "\\\\").replace('"', '\\"')
                lines.append(f'{k} = "{escaped}"')
            else:
                lines.append(f"{k} = {v}")
        lines.append("")
    _USER_CFG.write_text("\n".join(lines), encoding="utf-8")


def _lb_cfg() -> dict:
    return _read_cfg().get("leaderboard", {})


# ── Public config accessors ───────────────────────────────────────────────────

def is_opted_in() -> bool:
    return bool(_lb_cfg().get("opted_in", False))


def get_pseudonym() -> str:
    return _lb_cfg().get("pseudonym", "")


def get_user_token() -> str:
    return _lb_cfg().get("user_token", "")


def opt_in(pseudonym: str) -> str:
    """Enable participation. Returns the local UUID token."""
    cfg = _read_cfg()
    lb  = cfg.get("leaderboard", {})
    token = lb.get("user_token") or str(uuid.uuid4())
    lb.update(opted_in=True, pseudonym=pseudonym, user_token=token)
    cfg["leaderboard"] = lb
    _write_cfg(cfg)
    return token


def opt_out() -> None:
    cfg = _read_cfg()
    lb  = cfg.get("leaderboard", {})
    lb["opted_in"] = False
    cfg["leaderboard"] = lb
    _write_cfg(cfg)


# ── Local stats ───────────────────────────────────────────────────────────────

def peak_day_tokens(store) -> int:
    """All-time peak tokens consumed in a single calendar day."""
    rows = store.query(
        """
        SELECT COALESCE(SUM(t.input_tokens + t.output_tokens +
                            t.cache_creation_tokens + t.cache_read_tokens), 0) AS tok
        FROM sessions s
        JOIN turns t ON s.session_id = t.session_id
        GROUP BY date(s.started_at, 'localtime')
        ORDER BY tok DESC
        LIMIT 1
        """,
        (),
    )
    if rows:
        return int(rows[0]["tok"] or 0)
    return 0


# ── Supabase REST helpers ─────────────────────────────────────────────────────

def configured() -> bool:
    return (
        SUPABASE_URL      != "https://YOUR-PROJECT.supabase.co"
        and SUPABASE_ANON_KEY != "YOUR-ANON-KEY"
    )


def _get(path: str) -> list | None:
    if not configured():
        return None
    url = f"{SUPABASE_URL}/rest/v1/{path}"
    req = urllib.request.Request(url)
    req.add_header("apikey", SUPABASE_ANON_KEY)
    req.add_header("Authorization", f"Bearer {SUPABASE_ANON_KEY}")
    try:
        with urllib.request.urlopen(req, timeout=8) as r:
            return json.loads(r.read())
    except Exception:
        return None


def _upsert(body: dict) -> bool:
    if not configured():
        return False
    url  = f"{SUPABASE_URL}/rest/v1/{_TABLE}"
    data = json.dumps(body).encode()
    req  = urllib.request.Request(url, data=data, method="POST")
    req.add_header("apikey", SUPABASE_ANON_KEY)
    req.add_header("Authorization", f"Bearer {SUPABASE_ANON_KEY}")
    req.add_header("Content-Type", "application/json")
    req.add_header("Prefer", "resolution=merge-duplicates,return=minimal")
    try:
        with urllib.request.urlopen(req, timeout=8) as r:
            r.read()
        return True
    except Exception:
        return False


# ── Public API ────────────────────────────────────────────────────────────────

def fetch_top(limit: int = 10) -> list[dict]:
    """Fetch the top-N leaderboard entries sorted by peak_day descending."""
    result = _get(
        f"{_TABLE}?select=pseudonym,peak_day"
        f"&order=peak_day.desc&limit={limit}"
    )
    return result if isinstance(result, list) else []


def fetch_rank(token: str, my_peak: int) -> int | None:
    """Return 1-based rank for this token, or None on network error."""
    above = _get(
        f"{_TABLE}?select=user_token&peak_day=gt.{my_peak}"
    )
    if above is None:
        return None
    return len(above) + 1


def push_score(store) -> bool:
    """Submit or update the current user's peak-day score."""
    token     = get_user_token()
    pseudonym = get_pseudonym()
    if not token or not pseudonym:
        return False
    peak = peak_day_tokens(store)
    if peak == 0:
        return False
    return _upsert({
        "user_token": token,
        "pseudonym":  pseudonym,
        "peak_day":   peak,
        "updated_at": datetime.now(timezone.utc).isoformat(),
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


def save_cache(top: list, rank: int | None, peak: int) -> None:
    _CACHE.parent.mkdir(parents=True, exist_ok=True)
    _CACHE.write_text(json.dumps(
        {"top": top, "rank": rank, "peak": peak, "ts": time.time()}
    ))
