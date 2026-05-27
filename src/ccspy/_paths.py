"""Platform-aware runtime paths for ccspy.

macOS / Linux : config  → ~/.config/ccspy/
              : sessions → ~/.claude/projects/
Windows       : config  → %APPDATA%\\ccspy\\
              : sessions → %USERPROFILE%\\.claude\\projects\\   (Claude Code CLI)
                        or %APPDATA%\\Claude\\projects\\        (Claude desktop app)

Override env vars (all platforms):
  CLAUDE_HOME   — override Claude projects root (path must already end in 'projects'
                  or point at the parent; the parent /projects is appended here)
  CCSPY_CONFIG  — override ccspy config directory entirely
"""
from __future__ import annotations

import os
import sys
from pathlib import Path


def _config_dir() -> Path:
    override = os.environ.get("CCSPY_CONFIG")
    if override:
        return Path(override)
    if sys.platform == "win32":
        appdata = os.environ.get("APPDATA")
        base = Path(appdata) if appdata else Path.home() / "AppData" / "Roaming"
        return base / "ccspy"
    return Path.home() / ".config" / "ccspy"


def _claude_projects_dir() -> Path:
    if "CLAUDE_HOME" in os.environ:
        return Path(os.environ["CLAUDE_HOME"]) / "projects"

    # Claude Code CLI uses ~/.claude on all platforms (including Windows)
    cli_path = Path.home() / ".claude" / "projects"

    if sys.platform == "win32":
        # Claude desktop app (Electron) on Windows stores data in AppData
        appdata = os.environ.get("APPDATA")
        if appdata:
            desktop_path = Path(appdata) / "Claude" / "projects"
            if desktop_path.exists() and not cli_path.exists():
                return desktop_path
            # If both exist, prefer CLI path; callers that want both can
            # use CLAUDE_HOME to point at the one they need.

    return cli_path


def default_editor() -> str:
    """Return a usable editor command for the current platform."""
    env = os.environ.get("EDITOR") or os.environ.get("VISUAL")
    if env:
        return env
    return "notepad" if sys.platform == "win32" else "nano"


# Module-level constants used by the rest of the codebase
CONFIG_DIR      = _config_dir()
CLAUDE_PROJECTS = _claude_projects_dir()
