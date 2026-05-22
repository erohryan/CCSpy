"""Project bar chart panel."""
from __future__ import annotations

from textual.widget import Widget
from rich.text import Text

from ccspy.aggregator import ProjectStats
from ccspy.ui.widgets._format import bar, fmt_tokens, fmt_cost, fmt_pct

MAX_SHOWN = 6
BAR_WIDTH = 14
NAME_WIDTH = 18


class ProjectBarsPanel(Widget):
    """Left-column bar chart: token usage by project."""

    DEFAULT_CSS = "ProjectBarsPanel { width: 1fr; color: #2ac3de; padding: 0 2; }"

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self._projects: list[ProjectStats] = []
        self._filter: str = ""

    def update(self, projects: list[ProjectStats], filter_text: str = "") -> None:
        self._projects = projects
        self._filter = filter_text.lower()
        self.refresh()

    def render(self) -> Text:
        t = Text()
        t.append("BY PROJECT\n", style="bold #2ac3de")

        projects = self._projects
        if self._filter:
            projects = [p for p in projects if self._filter in p.project_name.lower()]

        if not projects:
            t.append("  no data in range", style="dim")
            return t

        for p in projects[:MAX_SHOWN]:
            name = p.project_name[:NAME_WIDTH].ljust(NAME_WIDTH)
            b = bar(p.pct, width=BAR_WIDTH)
            tok = fmt_tokens(p.total_tokens).rjust(6)
            pct = fmt_pct(p.pct)
            t.append(f"  {name} ", style="white")
            t.append(f"{b:<{BAR_WIDTH}}", style="#2ac3de")
            t.append(f" {tok}", style="white")
            t.append(f" {pct}\n", style="dim")

        remaining = len(projects) - MAX_SHOWN
        if remaining > 0:
            t.append(f"  … +{remaining} more\n", style="dim")

        return t
