"""Category bar chart panel."""
from __future__ import annotations

from textual.widget import Widget
from rich.text import Text

from ccspy.aggregator import CategoryStats
from ccspy.ui.widgets._format import (
    bar, stacked_bar, fmt_tokens, fmt_pct, SLICE_COLORS,
)

MAX_SHOWN   = 5
BAR_WIDTH   = 12
NAME_WIDTH  = 16
STACKED_W   = 34
LEGEND_NAME = 16


class CategoryBarsPanel(Widget):
    """Left-column bar chart: token usage by category (keyword rules)."""

    DEFAULT_CSS = "CategoryBarsPanel { width: 1fr; color: #2ac3de; padding: 0 2; }"

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self._categories: list[CategoryStats] = []
        self._stacked: bool = False

    def update(self, categories: list[CategoryStats]) -> None:
        self._categories = categories
        self.refresh()

    def set_mode(self, stacked: bool) -> None:
        self._stacked = stacked
        self.refresh()

    def render(self) -> Text:
        t = Text()
        t.append("BY CATEGORY", style="bold #2ac3de")
        if self._stacked:
            t.append("  ·stacked·", style="dim #444466")
        else:
            t.append(" (your rules)", style="dim")
        t.append("\n")

        if not self._categories:
            t.append("  no data — press e to edit rules", style="dim")
            return t

        # Separate uncategorized so it always goes last
        cats          = [c for c in self._categories if c.category != "uncategorized"]
        uncategorised = next((c for c in self._categories if c.category == "uncategorized"), None)

        shown     = cats[:MAX_SHOWN]
        remaining = cats[MAX_SHOWN:]

        if self._stacked:
            items = [(c.category, c.pct) for c in shown]
            if remaining:
                items.append(("other", sum(c.pct for c in remaining)))
            if uncategorised:
                items.append(("uncategorized", uncategorised.pct))

            t.append("\n  ")
            t.append_text(stacked_bar(items, width=STACKED_W))
            t.append("\n\n")

            for i, (name, pct) in enumerate(items):
                is_muted = name in ("other", "uncategorized")
                color    = SLICE_COLORS[i % len(SLICE_COLORS)]
                t.append("  ")
                t.append("▮ ", style=f"{'dim ' if is_muted else 'bold '}{color}")
                t.append(f"{name[:LEGEND_NAME]:<{LEGEND_NAME}}", style="dim" if is_muted else "white")
                t.append(f" {fmt_pct(pct)}\n", style="dim")

            t.append("  [e] edit rules\n", style="dim")
        else:
            for c in shown:
                name = c.category[:NAME_WIDTH].ljust(NAME_WIDTH)
                b    = bar(c.pct, width=BAR_WIDTH)
                tok  = fmt_tokens(c.total_tokens).rjust(6)
                pct  = fmt_pct(c.pct)
                t.append(f"  {name} ", style="white")
                t.append(f"{b:<{BAR_WIDTH}}", style="#2ac3de")
                t.append(f" {tok}", style="white")
                t.append(f" {pct}\n", style="dim")

            if uncategorised:
                pct = fmt_pct(uncategorised.pct).strip()
                t.append(f"  uncategorized {pct}  ", style="dim")
            t.append("[e] edit rules\n", style="dim")

        return t
