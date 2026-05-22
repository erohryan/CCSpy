"""Timing stats panel — processing time and user wait time."""
from __future__ import annotations

from textual.widget import Widget
from rich.text import Text

from ccspy.aggregator import TimingStats
from ccspy.ui.widgets._format import fmt_duration


class TimingPanel(Widget):
    """Shows avg/median processing time (Claude→you) and wait time (you→Claude)."""

    DEFAULT_CSS = "TimingPanel { height: 1; color: #7a7a9a; padding: 0 2; }"

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self._stats = TimingStats()

    def update(self, stats: TimingStats) -> None:
        self._stats = stats
        self.refresh()

    def render(self) -> Text:
        t = Text()
        t.append("TIMINGS", style="bold #7a7a9a")

        s = self._stats
        if s.samples == 0:
            t.append("  rebuild cache to populate", style="dim")
            return t

        t.append("  Claude ", style="dim")
        t.append(f"avg {fmt_duration(s.avg_processing_secs)}", style="white")
        t.append(f" median {fmt_duration(s.median_processing_secs)}", style="dim")

        t.append("     you ", style="dim")
        t.append(f"avg {fmt_duration(s.avg_wait_secs)}", style="white")
        t.append(f" median {fmt_duration(s.median_wait_secs)}", style="dim")

        t.append(f"     {s.samples} turns", style="dim")
        return t
