"""Project bar chart panel."""
from __future__ import annotations

from textual.widget import Widget
from rich.text import Text

from ccspy.aggregator import ProjectStats
from ccspy.ui.widgets._format import (
    bar, stacked_bar, fmt_tokens, fmt_cost, fmt_pct, SLICE_COLORS,
)

MAX_SHOWN   = 6
BAR_WIDTH   = 14
NAME_WIDTH  = 18
STACKED_W   = 34
LEGEND_NAME = 16


class ProjectBarsPanel(Widget):
    """Left-column bar chart: token usage by project."""

    DEFAULT_CSS = "ProjectBarsPanel { width: 1fr; color: #2ac3de; padding: 0 2; }"

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self._projects: list[ProjectStats] = []
        self._filter: str = ""
        self._stacked: bool = False

    def update(self, projects: list[ProjectStats], filter_text: str = "") -> None:
        self._projects = projects
        self._filter = filter_text.lower()
        self.refresh()

    def set_mode(self, stacked: bool) -> None:
        self._stacked = stacked
        self.refresh()

    def render(self) -> Text:
        t = Text()
        t.append("BY PROJECT", style="bold #2ac3de")
        if self._stacked:
            t.append("  ·stacked·\n", style="dim #444466")
        else:
            t.append("\n")

        projects = self._projects
        if self._filter:
            projects = [p for p in projects if self._filter in p.project_name.lower()]

        if not projects:
            t.append("  no data in range", style="dim")
            return t

        shown     = projects[:MAX_SHOWN]
        remaining = projects[MAX_SHOWN:]

        if self._stacked:
            items     = [(p.project_name, p.pct) for p in shown]
            other_pct = sum(p.pct for p in remaining)
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
            for p in shown:
                name = p.project_name[:NAME_WIDTH].ljust(NAME_WIDTH)
                b    = bar(p.pct, width=BAR_WIDTH)
                tok  = fmt_tokens(p.total_tokens).rjust(6)
                pct  = fmt_pct(p.pct)
                t.append(f"  {name} ", style="white")
                t.append(f"{b:<{BAR_WIDTH}}", style="#2ac3de")
                t.append(f" {tok}", style="white")
                t.append(f" {pct}\n", style="dim")

            if remaining:
                t.append(f"  … +{len(remaining)} more\n", style="dim")

        return t
