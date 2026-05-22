"""Model bar chart panel."""
from __future__ import annotations

from textual.widget import Widget
from rich.text import Text

from ccspy.aggregator import ModelStats
from ccspy.ui.widgets._format import bar, fmt_tokens, fmt_cost, fmt_pct, short_model

MAX_SHOWN = 6
BAR_WIDTH = 14
NAME_WIDTH = 12


class ModelBarsPanel(Widget):
    """Right-column bar chart: token usage by model (magenta bars)."""

    DEFAULT_CSS = "ModelBarsPanel { width: 1fr; color: #c678dd; padding: 0 2; }"

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self._models: list[ModelStats] = []

    def update(self, models: list[ModelStats]) -> None:
        self._models = models
        self.refresh()

    def render(self) -> Text:
        t = Text()
        t.append("BY MODEL\n", style="bold #c678dd")

        if not self._models:
            t.append("  no data in range", style="dim")
            return t

        for m in self._models[:MAX_SHOWN]:
            if m.model == "<synthetic>":
                continue
            name = short_model(m.model)[:NAME_WIDTH].ljust(NAME_WIDTH)
            b = bar(m.pct, width=BAR_WIDTH)
            tok = fmt_tokens(m.total_tokens).rjust(6)
            pct = fmt_pct(m.pct)
            cost = fmt_cost(m.est_api_cost_usd).rjust(7)
            t.append(f"  {name} ", style="white")
            t.append(f"{b:<{BAR_WIDTH}}", style="#c678dd")
            t.append(f" {tok}", style="white")
            t.append(f" {pct}", style="dim")
            t.append(f" {cost}\n", style="#e0823a")

        return t
