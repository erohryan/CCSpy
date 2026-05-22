"""Totals panel — aggregate token counts and api-equiv cost."""
from __future__ import annotations

from textual.widget import Widget
from rich.text import Text

from ccspy.aggregator import RangeTotals
from ccspy.ui.widgets._format import fmt_tokens, fmt_cost, delta_str


class TotalsPanel(Widget):
    """Two-line summary: token counts + cost, then breakdown + delta vs prev period."""

    DEFAULT_CSS = "TotalsPanel { height: 3; color: #d4a853; padding: 0 2; }"

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self._totals: RangeTotals | None = None
        self._prev: RangeTotals | None = None

    def update(self, totals: RangeTotals, prev_totals: RangeTotals) -> None:
        self._totals = totals
        self._prev = prev_totals
        self.refresh()

    def render(self) -> Text:
        t = self._totals
        p = self._prev
        out = Text()

        if not t:
            out.append("TOTALS   (loading…)", style="dim")
            return out

        # Line 1: headline numbers
        out.append("TOTALS", style="bold #d4a853")
        out.append("    ")
        out.append(fmt_tokens(t.total_tokens), style="bold white")
        out.append(" tokens", style="#d4a853")

        cost_str = fmt_cost(t.est_api_cost_usd)
        out.append(f"   ≈ {cost_str}", style="#e0823a")
        out.append(" api-equiv", style="dim")
        out.append(f"   {t.session_count}", style="white")
        out.append(" sessions", style="dim")
        out.append(f"   {t.project_count}", style="white")
        out.append(" projects", style="dim")

        out.append("\n")

        # Line 2: breakdown + delta
        out.append("        ", style="")
        if p and p.total_tokens > 0:
            d = delta_str(t.total_tokens, p.total_tokens)
            if d:
                style = "#44cf6c" if t.total_tokens >= p.total_tokens else "#e0823a"
                out.append(d, style=style)
                out.append(" vs prev period", style="dim")
                out.append("     ", style="")

        out.append("in:", style="dim")
        out.append(f" {fmt_tokens(t.input_tokens)}", style="#7a7a9a")
        out.append("  out:", style="dim")
        out.append(f" {fmt_tokens(t.output_tokens)}", style="#7a7a9a")
        out.append("  cache-w:", style="dim")
        out.append(f" {fmt_tokens(t.cache_creation_tokens)}", style="#7a7a9a")
        out.append("  cache-r:", style="dim")
        out.append(f" {fmt_tokens(t.cache_read_tokens)}", style="#7a7a9a")

        out.append("\n")
        return out
