"""Range selector row."""
from __future__ import annotations

from textual.widget import Widget
from rich.text import Text

RANGES = [(0, "[1] today"), (7, "[2] 7d"), (30, "[3] 30d")]


class RangeRow(Widget):
    """Shows [1] 1d  ▸ [2] 7d  [3] 30d  [c] custom with current highlighted."""

    DEFAULT_CSS = "RangeRow { height: 1; color: #7a7a9a; padding: 0 2; }"

    def __init__(self, range_days: int = 7, **kwargs) -> None:
        super().__init__(**kwargs)
        self._range_days = range_days

    def update(self, range_days: int) -> None:
        self._range_days = range_days
        self.refresh()

    def render(self) -> Text:
        t = Text()
        t.append("RANGE", style="bold #7a7a9a")
        t.append("   ")
        for days, label in RANGES:
            if days == self._range_days:
                t.append(f"▸ {label}", style="bold white")
            else:
                t.append(f"  {label}", style="dim")
            t.append("   ")
        t.append("[c] custom", style="dim")
        return t
