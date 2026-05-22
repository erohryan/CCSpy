"""Help overlay — keyboard shortcut reference."""
from __future__ import annotations

from textual.app import ComposeResult
from textual.binding import Binding
from textual.screen import ModalScreen
from textual.widgets import Static
from textual.containers import Vertical

HELP_TEXT = """\
 ccspy keyboard shortcuts
 ─────────────────────────────────────────────────────
  1 / 2 / 3    Switch range to 1d / 7d / 30d
  c            Custom date range
  :            Command palette (fuzzy search all actions)
  p            Project drill-down
  s            Session drill-down (last 50 sessions)
  t            Tool breakdown drill-down
  e            Edit category rules in $EDITOR
  x            Export current view to CSV
  /            Filter by project name substring
  r            Force reload + cache sync
  ?            Show this help
  q / Ctrl-C   Quit

 Data source:  ~/.claude/projects/**/*.jsonl  (read-only)
 Cache:        ~/.config/ccspy/cache.db
 Categories:   ~/.config/ccspy/categories.toml
 Logs:         ~/.config/ccspy/ccspy.log

 ccspy is read-only — it never modifies your Claude Code data.
 All $ figures are api-equiv estimates; Pro/Max users pay flat rate.
 ─────────────────────────────────────────────────────
 Press Esc or ? to close\
"""


class HelpModal(ModalScreen):
    """Full-screen help overlay."""

    BINDINGS = [
        Binding("escape", "dismiss", "Close", show=False),
        Binding("?", "dismiss", "Close", show=False),
    ]

    DEFAULT_CSS = """
    HelpModal {
        align: center middle;
    }
    HelpModal > Vertical {
        width: 60;
        height: auto;
        background: #1a1a2e;
        border: solid #444466;
        padding: 1 2;
    }
    HelpModal Static {
        color: #7a7a9a;
    }
    """

    def compose(self) -> ComposeResult:
        with Vertical():
            yield Static(HELP_TEXT)
