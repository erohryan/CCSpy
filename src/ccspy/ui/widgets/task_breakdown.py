"""Task breakdown panel — per-project task count, duration, plan vs execute."""
from __future__ import annotations

from textual.widget import Widget
from rich.text import Text

from ccspy.aggregator import ProjectTaskStats
from ccspy.ui.widgets._format import fmt_duration

MAX_SHOWN = 6
BAR_WIDTH = 10
NAME_WIDTH = 14

PLAN_CHAR = "░"
EXEC_CHAR = "▓"


class TaskBreakdownPanel(Widget):
    """Right-column panel: per-project task count, avg duration, plan/execute split."""

    DEFAULT_CSS = "TaskBreakdownPanel { width: 1fr; color: #7a7a9a; padding: 0 2; }"

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self._stats: list[ProjectTaskStats] = []

    def update(self, stats: list[ProjectTaskStats]) -> None:
        self._stats = stats
        self.refresh()

    def render(self) -> Text:
        t = Text()
        t.append("TASKS  ", style="bold #7a7a9a")
        t.append(f"{PLAN_CHAR}plan ", style="dim")
        t.append(f"{EXEC_CHAR}execute\n", style="dim")

        if not self._stats:
            t.append("  no data in range", style="dim")
            return t

        for s in self._stats[:MAX_SHOWN]:
            name = s.project_name[:NAME_WIDTH].ljust(NAME_WIDTH)

            # Two-tone bar: plan then execute
            exec_filled = max(0, round(s.execute_pct / 100 * BAR_WIDTH))
            plan_filled = BAR_WIDTH - exec_filled
            b_plan = PLAN_CHAR * plan_filled
            b_exec = EXEC_CHAR * exec_filled

            tasks = str(s.task_count)
            dur = fmt_duration(s.avg_duration_secs).rjust(7)

            t.append(f"  {name} ", style="white")
            t.append(b_plan, style="#555577")
            t.append(b_exec, style="#9999cc")
            t.append(f" {tasks} msgs", style="white")
            t.append(f" {dur} avg\n", style="dim")

        return t
