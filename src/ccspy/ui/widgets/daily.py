"""Daily usage sparkline panel."""
from __future__ import annotations

from textual.widget import Widget
from rich.text import Text

from ccspy.aggregator import DailyBucket
from ccspy.ui.widgets._format import spark, fmt_tokens, fmt_cost

SPARK_WIDTH = 30


class DailyPanel(Widget):
    """Sparkline of daily token totals with peak annotation."""

    DEFAULT_CSS = "DailyPanel { height: 2; color: #2ac3de; padding: 0 2; }"

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self._daily: list[DailyBucket] = []

    def update(self, daily: list[DailyBucket]) -> None:
        self._daily = daily
        self.refresh()

    def render(self) -> Text:
        t = Text()
        daily = self._daily

        t.append("DAILY", style="bold #2ac3de")
        t.append("     ", style="")

        if not daily:
            t.append("no data in range — try [3] 30d", style="dim")
            return t

        counts = [b.total_tokens for b in daily]
        bars = spark(counts, width=min(SPARK_WIDTH, len(counts)))
        t.append(bars, style="#2ac3de")

        peak = max(daily, key=lambda b: b.total_tokens)
        t.append(f"   peak: ", style="dim")
        t.append(peak.date, style="#e0823a")
        t.append(f" {fmt_tokens(peak.total_tokens)}", style="bold #e0823a")

        cost_total = sum(b.est_api_cost_usd or 0 for b in daily)
        if cost_total > 0:
            t.append(f"   {fmt_cost(cost_total)} api-equiv", style="dim")

        t.append("\n")
        return t
