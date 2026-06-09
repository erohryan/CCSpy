"""Totals panel — aggregate token counts, api-equiv cost, and plan break-even."""
from __future__ import annotations

from textual.widget import Widget
from rich.text import Text

from ccspy.aggregator import RangeTotals
from ccspy.ui.widgets._format import fmt_tokens, fmt_cost, delta_str


class TotalsPanel(Widget):
    """Three-line summary: headline · breakdown · plan break-even."""

    DEFAULT_CSS = "TotalsPanel { height: 4; color: #d4a853; padding: 0 2; }"

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self._totals: RangeTotals | None = None
        self._prev: RangeTotals | None = None
        self._range_days: int = 7
        self._plan_name: str = ""
        self._plan_cost: float | None = None

    def update(
        self,
        totals: RangeTotals,
        prev_totals: RangeTotals,
        range_days: int = 7,
        plan_name: str = "",
        plan_monthly_cost: float | None = None,
    ) -> None:
        self._totals     = totals
        self._prev       = prev_totals
        self._range_days = range_days
        self._plan_name  = plan_name
        self._plan_cost  = plan_monthly_cost
        self.refresh()

    def render(self) -> Text:
        t   = self._totals
        p   = self._prev
        out = Text()

        if not t:
            out.append("TOTALS   (loading…)", style="dim")
            return out

        # ── Line 1: headline numbers ────────────────────────────────────────
        out.append("TOTALS", style="bold #d4a853")
        out.append("    ")
        out.append(fmt_tokens(t.total_tokens), style="bold white")
        out.append(" tokens", style="#d4a853")
        out.append(f"   ≈ {fmt_cost(t.est_api_cost_usd)}", style="#e0823a")
        out.append(" api-equiv", style="dim")
        out.append(f"   {t.session_count}", style="white")
        out.append(" sessions", style="dim")
        out.append(f"   {t.project_count}", style="white")
        out.append(" projects", style="dim")
        out.append("\n")

        # ── Line 2: breakdown + delta vs prev ───────────────────────────────
        out.append("        ")
        if p and p.total_tokens > 0:
            d = delta_str(t.total_tokens, p.total_tokens)
            if d:
                style = "#44cf6c" if t.total_tokens >= p.total_tokens else "#e0823a"
                out.append(d, style=style)
                out.append(" vs prev period", style="dim")
                out.append("     ")
        out.append("in:", style="dim")
        out.append(f" {fmt_tokens(t.input_tokens)}", style="#7a7a9a")
        out.append("  out:", style="dim")
        out.append(f" {fmt_tokens(t.output_tokens)}", style="#7a7a9a")
        out.append("  cache-w:", style="dim")
        out.append(f" {fmt_tokens(t.cache_creation_tokens)}", style="#7a7a9a")
        out.append("  cache-r:", style="dim")
        out.append(f" {fmt_tokens(t.cache_read_tokens)}", style="#7a7a9a")
        out.append("\n")

        # ── Line 3: plan break-even ─────────────────────────────────────────
        out.append("        ")
        if self._plan_cost is not None and self._plan_cost > 0:
            from ccspy.plan import quota_for_range
            quota        = quota_for_range(self._plan_cost, self._range_days)
            used         = t.est_api_cost_usd or 0.0
            pct          = used / quota * 100 if quota > 0 else 0.0
            period_label = "today" if self._range_days == 0 else f"{self._range_days}d"

            if pct >= 100:
                color  = "#44cf6c"
                status = f"+{fmt_cost(used - quota)} ahead"
            elif pct >= 50:
                color  = "#e0823a"
                status = f"{fmt_cost(quota - used)} to break-even"
            else:
                color  = "#cc4444"
                status = f"{fmt_cost(quota - used)} to break-even"

            BAR_W  = 10
            filled = min(BAR_W, max(0, round(pct / 100 * BAR_W)))
            empty  = BAR_W - filled

            out.append(self._plan_name.upper() or "PLAN", style=f"bold {color}")
            out.append(f"  {period_label} quota ", style="dim")
            out.append(fmt_cost(quota), style="white")
            out.append("  used ", style="dim")
            out.append(fmt_cost(used), style="white")
            out.append("   ")
            out.append("█" * filled, style=color)
            out.append("░" * empty,  style="dim #2d2d4e")
            out.append(f"  {pct:.0f}%  ", style=f"bold {color}")
            out.append(status, style=color)
        else:
            out.append("no plan set", style="dim #444466")
            out.append("  ·  press ", style="dim #444466")
            out.append("$", style="#9999cc")
            out.append(" to configure your subscription for break-even tracking", style="dim #444466")
        out.append("\n")

        return out
