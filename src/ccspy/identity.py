"""Identity management for ccspy.

Owns the [identity] section of user.toml. No circular imports —
does not import from leaderboard or team.

user.toml layout
----------------
[identity]
user_token = "uuid"
pseudonym  = "turbodev"
claim_code = "swift-wolf-4829"

[leaderboard]
opted_in = true

[team]
team_id   = "uuid"
team_name = "brave_cobras"
role      = "admin"
"""
from __future__ import annotations

import hashlib
import random
import uuid
from pathlib import Path

from ccspy._paths import CONFIG_DIR
from ccspy import _supabase as sb

_USER_CFG = CONFIG_DIR / "user.toml"

# ── Word lists for claim codes ────────────────────────────────────────────────

_ADJECTIVES = [
    "swift", "brave", "calm", "dark", "eager",
    "fierce", "gentle", "happy", "idle", "jolly",
    "keen", "lively", "merry", "noble", "odd",
    "proud", "quiet", "rapid", "sharp", "tall",
    "ultra", "vivid", "warm", "xenial", "young",
    "zesty", "amber", "crisp", "dusty", "frosty",
]

_ANIMALS = [
    "wolf", "hawk", "bear", "deer", "crow",
    "lynx", "mole", "newt", "orca", "puma",
    "quail", "rook", "seal", "toad", "vole",
    "wasp", "yak", "zebe", "bison", "crane",
    "dingo", "eagle", "finch", "goat", "heron",
    "ibis", "jackal", "kite", "lemur", "moose",
]


# ── TOML I/O ──────────────────────────────────────────────────────────────────

def _load_toml() -> dict:
    """Read user.toml; return empty dict on any error."""
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


def _save_toml(data: dict) -> None:
    """Write a multi-section dict as TOML."""
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


# ── Public section helpers ────────────────────────────────────────────────────

def read_section(section: str) -> dict:
    """Return the contents of one [section] from user.toml."""
    return _load_toml().get(section, {})


def update_section(section: str, values: dict) -> None:
    """Merge *values* into [section] and rewrite user.toml."""
    data = _load_toml()
    existing = data.get(section, {})
    existing.update(values)
    data[section] = existing
    _save_toml(data)


# ── Identity state ────────────────────────────────────────────────────────────

def is_registered() -> bool:
    """Return True if user_token is present in [identity]."""
    return bool(read_section("identity").get("user_token", ""))


def get_user_token() -> str:
    return read_section("identity").get("user_token", "")


def get_pseudonym() -> str:
    return read_section("identity").get("pseudonym", "")


def get_claim_code() -> str:
    return read_section("identity").get("claim_code", "")


# ── Claim code helpers ────────────────────────────────────────────────────────

def _generate_claim_code() -> str:
    adj    = random.choice(_ADJECTIVES)
    animal = random.choice(_ANIMALS)
    num    = random.randint(1000, 9999)
    return f"{adj}-{animal}-{num}"


def _hash_code(code: str) -> str:
    return hashlib.sha256(code.encode()).hexdigest()


# ── Registration ──────────────────────────────────────────────────────────────

def register(pseudonym: str) -> str:
    """Create a new identity locally and push to identity_claims.

    Generates a UUID user_token and a claim code, writes [identity] to
    user.toml, pushes to the identity_claims table.

    Returns the claim_code (plain text) — caller should show this once.
    """
    token      = str(uuid.uuid4())
    claim_code = _generate_claim_code()
    code_hash  = _hash_code(claim_code)

    # Push to Supabase (best-effort — if offline, still registers locally)
    sb.post(
        "identity_claims",
        {
            "claim_code_hash": code_hash,
            "user_token": token,
            "pseudonym":  pseudonym,
        },
    )

    update_section("identity", {
        "user_token":  token,
        "pseudonym":   pseudonym,
        "claim_code":  claim_code,
    })
    return claim_code


def sync_from_code(code: str) -> bool:
    """Look up a claim code in Supabase and write local [identity].

    Returns True if the identity was found and written, False otherwise.
    """
    code_hash = _hash_code(code.strip())
    result = sb.get(
        f"identity_claims?claim_code_hash=eq.{code_hash}"
        "&select=user_token,pseudonym&limit=1"
    )
    if not result or not isinstance(result, list) or len(result) == 0:
        return False
    row = result[0]
    token     = row.get("user_token", "")
    pseudonym = row.get("pseudonym", "")
    if not token:
        return False
    update_section("identity", {
        "user_token": token,
        "pseudonym":  pseudonym,
        "claim_code": code.strip(),
    })
    return True
