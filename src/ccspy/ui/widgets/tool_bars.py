"""Tool usage bar chart panel."""
from __future__ import annotations

from textual.widget import Widget
from rich.text import Text

from ccspy.aggregator import ToolStats
from ccspy.ui.widgets._format import bar, fmt_pct, TOOL_BAR_CHAR

MAX_SHOWN = 6
BAR_WIDTH = 12
NAME_WIDTH = 12


class ToolBarsPanel(Widget):
    """Right-column bar chart: tool call frequency."""

    DEFAULT_CSS = "ToolBarsPanel { width: 1fr; color: #7a7a9a; padding: 0 2; }"

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self._tools: list[ToolStats] = []

    def update(self, tools: list[ToolStats]) -> None:
        self._tools = tools
        self.refresh()

    def render(self) -> Text:
        t = Text()
        t.append("TOOL USE\n", style="bold #7a7a9a")

        if not self._tools:
            t.append("  no data in range", style="dim")
            return t

        for tool in self._tools[:MAX_SHOWN]:
            name = tool.tool_name[:NAME_WIDTH].ljust(NAME_WIDTH)
            b = bar(tool.pct, width=BAR_WIDTH, char=TOOL_BAR_CHAR)
            cnt = str(tool.call_count).rjust(5)
            pct = fmt_pct(tool.pct)
            t.append(f"  {name} ", style="white")
            t.append(f"{b:<{BAR_WIDTH}}", style="#7a7a9a")
            t.append(f" {cnt}", style="white")
            t.append(f" {pct}\n", style="dim")

        return t
