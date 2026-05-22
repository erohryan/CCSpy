"""Subagent statistics panel."""
from __future__ import annotations

from textual.widget import Widget
from rich.text import Text

from ccspy.aggregator import SubagentStats


class SubagentStatsPanel(Widget):
    """One-line summary of subagent spawn statistics."""

    DEFAULT_CSS = "SubagentStatsPanel { height: 1; color: #7a7a9a; padding: 0 2; }"

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self._stats: SubagentStats | None = None

    def update(self, stats: SubagentStats) -> None:
        self._stats = stats
        self.refresh()

    def render(self) -> Text:
        t = Text()
        s = self._stats
        t.append("SUBAGENTS", style="bold #7a7a9a")
        t.append("    ", style="")
        if not s or s.total_spawned == 0:
            t.append("none in range", style="dim")
        else:
            t.append(str(s.total_spawned), style="white")
            t.append(" spawned", style="dim")
            t.append(f"   avg ", style="dim")
            t.append(str(s.avg_per_session), style="white")
            t.append(" per session", style="dim")
        return t
