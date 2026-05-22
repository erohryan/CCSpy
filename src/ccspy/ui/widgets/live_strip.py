"""Live session strip — shows active sessions with sparklines."""
from __future__ import annotations

import time
from textual.widget import Widget
from rich.text import Text

from ccspy.live import LiveSession
from ccspy.ui.widgets._format import fmt_tokens, spark, short_model, age_str

MAX_SHOWN = 4


class LiveStrip(Widget):
    """Top strip showing up to 4 currently active Claude Code sessions."""

    DEFAULT_CSS = "LiveStrip { height: 2; color: #44cf6c; padding: 0 2; }"

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self._sessions: list[LiveSession] = []

    def update(self, sessions: list[LiveSession]) -> None:
        self._sessions = sessions
        self.refresh()

    def render(self) -> Text:
        sessions = self._sessions
        t = Text()

        if not sessions:
            t.append("● LIVE", style="green")
            t.append("  watching…", style="dim")
            return t

        count = len(sessions)
        overflow = max(0, count - MAX_SHOWN)
        shown = sessions[:MAX_SHOWN]

        t.append("● LIVE", style="bold green")
        t.append(f"  {count} active", style="green")

        for s in shown:
            model_short = short_model(s.model)
            tok = fmt_tokens(s.total_tokens)
            sp = spark(s.recent_token_counts, width=6)
            age = age_str(s.age_seconds)
            t.append("   ", style="")
            t.append(s.project_name, style="bold white")
            t.append(f" {model_short}", style="dim")
            t.append(f" {tok}", style="white")
            t.append(f" {sp}", style="green")
            t.append(f" {age}", style="dim")

        if overflow:
            t.append(f"   +{overflow} more", style="dim")

        return t
