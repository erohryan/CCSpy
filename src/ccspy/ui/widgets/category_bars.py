"""Category bar chart panel."""
from __future__ import annotations

from textual.widget import Widget
from rich.text import Text

from ccspy.aggregator import CategoryStats
from ccspy.ui.widgets._format import bar, fmt_tokens, fmt_pct

MAX_SHOWN = 5
BAR_WIDTH = 12
NAME_WIDTH = 16


class CategoryBarsPanel(Widget):
    """Left-column bar chart: token usage by category (keyword rules)."""

    DEFAULT_CSS = "CategoryBarsPanel { width: 1fr; color: #2ac3de; padding: 0 2; }"

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self._categories: list[CategoryStats] = []

    def update(self, categories: list[CategoryStats]) -> None:
        self._categories = categories
        self.refresh()

    def render(self) -> Text:
        t = Text()
        t.append("BY CATEGORY", style="bold #2ac3de")
        t.append(" (your rules)\n", style="dim")

        if not self._categories:
            t.append("  no data — press e to edit rules", style="dim")
            return t

        for c in self._categories[:MAX_SHOWN]:
            name = c.category[:NAME_WIDTH].ljust(NAME_WIDTH)
            b = bar(c.pct, width=BAR_WIDTH)
            tok = fmt_tokens(c.total_tokens).rjust(6)
            pct = fmt_pct(c.pct)
            t.append(f"  {name} ", style="white")
            t.append(f"{b:<{BAR_WIDTH}}", style="#2ac3de")
            t.append(f" {tok}", style="white")
            t.append(f" {pct}\n", style="dim")

        # Footer hint
        uncategorised = next((c for c in self._categories if c.category == "uncategorized"), None)
        if uncategorised:
            pct = fmt_pct(uncategorised.pct).strip()
            t.append(f"  uncategorized {pct}  ", style="dim")
        t.append("[e] edit rules\n", style="dim")

        return t
