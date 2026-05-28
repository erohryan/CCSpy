"""Shared Supabase HTTP client — no dependencies on other ccspy modules.

Uses urllib only (no requests). All functions catch all exceptions and
return None / False on error.
"""
from __future__ import annotations

import json
import urllib.request
import urllib.error

SUPABASE_URL = "https://jdldtbtwubmderonvaqv.supabase.co"
SUPABASE_ANON_KEY = (
    "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9"
    ".eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImpkbGR0YnR3dWJtZGVyb252YXF2Iiwi"
    "cm9sZSI6ImFub24iLCJpYXQiOjE3Nzk5NDQxNjMsImV4cCI6MjA5NTUyMDE2M30"
    "._w53L7C8D7gHOSuNMLR-J30Rqqipkte8rP9drq8GhiQ"
)

_BASE = SUPABASE_URL + "/rest/v1/"


def _headers(extra: dict | None = None) -> dict:
    h = {
        "apikey": SUPABASE_ANON_KEY,
        "Authorization": f"Bearer {SUPABASE_ANON_KEY}",
        "Content-Type": "application/json",
    }
    if extra:
        h.update(extra)
    return h


def get(path: str) -> list | None:
    """GET /rest/v1/{path}. Returns list on success, None on error."""
    url = _BASE + path
    req = urllib.request.Request(url)
    for k, v in _headers().items():
        req.add_header(k, v)
    try:
        with urllib.request.urlopen(req, timeout=8) as r:
            body = r.read()
            if not body:
                return []
            return json.loads(body)
    except Exception:
        return None


def post(path: str, body: dict, returning: bool = False) -> list | dict | bool | None:
    """POST /rest/v1/{path}.

    If returning=True uses Prefer: return=representation and returns parsed JSON.
    Otherwise uses Prefer: return=minimal and returns True on success.
    Returns None on error.
    """
    url  = _BASE + path
    data = json.dumps(body).encode()
    prefer = "return=representation" if returning else "return=minimal"
    req  = urllib.request.Request(url, data=data, method="POST")
    for k, v in _headers({"Prefer": prefer}).items():
        req.add_header(k, v)
    try:
        with urllib.request.urlopen(req, timeout=8) as r:
            resp_body = r.read()
            if returning:
                return json.loads(resp_body) if resp_body else []
            return True
    except Exception:
        return None


def upsert(path: str, body: dict) -> bool:
    """POST with Prefer: resolution=merge-duplicates,return=minimal.

    Returns True on success, False on error.
    """
    url  = _BASE + path
    data = json.dumps(body).encode()
    req  = urllib.request.Request(url, data=data, method="POST")
    for k, v in _headers(
        {"Prefer": "resolution=merge-duplicates,return=minimal"}
    ).items():
        req.add_header(k, v)
    try:
        with urllib.request.urlopen(req, timeout=8) as r:
            r.read()
        return True
    except Exception:
        return False


def delete(path: str) -> bool:
    """DELETE /rest/v1/{path}. Returns True on success, False on error."""
    url = _BASE + path
    req = urllib.request.Request(url, method="DELETE")
    for k, v in _headers().items():
        req.add_header(k, v)
    try:
        with urllib.request.urlopen(req, timeout=8) as r:
            r.read()
        return True
    except Exception:
        return False
