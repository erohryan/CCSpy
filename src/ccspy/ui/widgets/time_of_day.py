"""Time-of-day sparkline panel."""
from __future__ import annotations

from textual.widget import Widget
from rich.text import Text

from ccspy.aggregator import HourBucket
from ccspy.ui.widgets._format import spark

LABEL_HOURS = [0, 3, 6, 9, 12, 15, 18, 21]


class TimeOfDayPanel(Widget):
    """24-bar sparkline annotated with hour labels and peak window."""

    DEFAULT_CSS = "TimeOfDayPanel { height: 2; color: #7a7a9a; padding: 0 2; }"

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self._by_hour: list[HourBucket] = []

    def update(self, by_hour: list[HourBucket]) -> None:
        self._by_hour = by_hour
        self.refresh()

    def render(self) -> Text:
        t = Text()
        t.append("TIME-OF-DAY", style="bold #7a7a9a")
        t.append("  ", style="")

        hours = self._by_hour
        if not hours or not any(h.total_tokens for h in hours):
            t.append("no activity data", style="dim")
            return t

        # Build annotated sparkline with hour labels every 3 hours
        counts = [h.total_tokens for h in hours]
        bars = spark(counts)

        # Interleave hour labels with sparkline bars
        for i, (h, bar_char) in enumerate(zip(hours, bars)):
            if h.hour in LABEL_HOURS:
                t.append(f"{h.hour:02d} ", style="dim")
            t.append(bar_char, style="#7a7a9a")

        peak = max(hours, key=lambda h: h.total_tokens)
        t.append(f"   peak: ", style="dim")
        t.append(f"{peak.hour:02d}:00", style="#e0823a")

        t.append("\n")
        return t
