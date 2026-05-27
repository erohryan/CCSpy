"""Model bar chart panel."""
from __future__ import annotations

from textual.widget import Widget
from rich.text import Text

from ccspy.aggregator import ModelStats
from ccspy.ui.widgets._format import (
    bar, stacked_bar, fmt_tokens, fmt_cost, fmt_pct, short_model, SLICE_COLORS,
)

MAX_SHOWN   = 6
BAR_WIDTH   = 14
NAME_WIDTH  = 12
STACKED_W   = 34
LEGEND_NAME = 16


class ModelBarsPanel(Widget):
    """Right-column bar chart: token usage by model (magenta bars)."""

    DEFAULT_CSS = "ModelBarsPanel { width: 1fr; color: #c678dd; padding: 0 2; }"

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self._models: list[ModelStats] = []
        self._stacked: bool = False

    def update(self, models: list[ModelStats]) -> None:
        self._models = models
        self.refresh()

    def set_mode(self, stacked: bool) -> None:
        self._stacked = stacked
        self.refresh()

    def render(self) -> Text:
        t = Text()
        t.append("BY MODEL", style="bold #c678dd")
        if self._stacked:
            t.append("  ·stacked·\n", style="dim #444466")
        else:
            t.append("\n")

        models = [m for m in self._models if m.model != "<synthetic>"]

        if not models:
            t.append("  no data in range", style="dim")
            return t

        shown     = models[:MAX_SHOWN]
        remaining = models[MAX_SHOWN:]

        if self._stacked:
            items     = [(short_model(m.model), m.pct) for m in shown]
            other_pct = sum(m.pct for m in remaining)
            if other_pct > 0.5:
                items.append(("other", other_pct))

            t.append("\n  ")
            t.append_text(stacked_bar(items, width=STACKED_W))
            t.append("\n\n")

            for i, (name, pct) in enumerate(items):
                is_other = name == "other"
                color = SLICE_COLORS[i % len(SLICE_COLORS)]
                t.append("  ")
                t.append("▮ ", style=f"{'dim ' if is_other else 'bold '}{color}")
                t.append(f"{name[:LEGEND_NAME]:<{LEGEND_NAME}}", style="dim" if is_other else "white")
                t.append(f" {fmt_pct(pct)}\n", style="dim")
        else:
            for m in shown:
                name = short_model(m.model)[:NAME_WIDTH].ljust(NAME_WIDTH)
                b    = bar(m.pct, width=BAR_WIDTH)
                tok  = fmt_tokens(m.total_tokens).rjust(6)
                pct  = fmt_pct(m.pct)
                cost = fmt_cost(m.est_api_cost_usd).rjust(7)
                t.append(f"  {name} ", style="white")
                t.append(f"{b:<{BAR_WIDTH}}", style="#c678dd")
                t.append(f" {tok}", style="white")
                t.append(f" {pct}", style="dim")
                t.append(f" {cost}\n", style="#e0823a")

        return t
