"""Main dashboard screen — six panel groups on a single screen."""
from __future__ import annotations

import subprocess
import time
from pathlib import Path

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal
from textual.screen import Screen
from textual.widget import Widget
from textual.widgets import Static
from rich.text import Text

from ccspy._paths import CONFIG_DIR, default_editor
from ccspy.aggregator import Aggregator, DashboardData
from ccspy.categories import ensure_user_categories, load_rules
from ccspy.live import get_live_sessions
from ccspy.pricing import pricing_updated
from ccspy.store import Store
from ccspy.ui.widgets.live_strip import LiveStrip
from ccspy.ui.widgets.range_row import RangeRow
from ccspy.ui.widgets.totals import TotalsPanel
from ccspy.ui.widgets.daily import DailyPanel
from ccspy.ui.widgets.project_bars import ProjectBarsPanel
from ccspy.ui.widgets.model_bars import ModelBarsPanel
from ccspy.ui.widgets.category_bars import CategoryBarsPanel
from ccspy.ui.widgets.tool_bars import ToolBarsPanel
from ccspy.ui.widgets.task_breakdown import TaskBreakdownPanel
from ccspy.ui.widgets.time_of_day import TimeOfDayPanel
from ccspy.ui.widgets.subagent_stats import SubagentStatsPanel
from ccspy.ui.widgets.timing import TimingPanel

CONFIG_CATEGORIES = CONFIG_DIR / "categories.toml"
LIVE_REFRESH_SECONDS = 5.0


class _Header(Widget):
    """Top status bar: title, range, live status, last-updated timestamp."""

    DEFAULT_CSS = "_Header { height: 1; background: #12122a; color: #7a7a9a; padding: 0 2; }"

    def __init__(self, range_days: int = 7, **kwargs) -> None:
        super().__init__(**kwargs)
        self._range_days = range_days
        self._last_sync: float = time.time()
        self._prices_date = pricing_updated()

    def update(self, range_days: int, last_sync: float) -> None:
        self._range_days = range_days
        self._last_sync = last_sync
        self.refresh()

    def render(self) -> Text:
        elapsed = int(time.time() - self._last_sync)
        if elapsed < 60:
            age = f"{elapsed}s ago"
        else:
            age = f"{elapsed // 60}m ago"

        t = Text()
        t.append("ccspy", style="bold white")
        range_label = "today" if self._range_days == 0 else f"{self._range_days}d"
        t.append(f" · {range_label} · watching · updated {age}", style="#7a7a9a")
        t.append(f"   prices as of {self._prices_date}", style="dim")
        t.append("   ")
        t.append("? help", style="dim")
        t.append("  ")
        t.append("q quit", style="dim")
        return t


class _Separator(Static):
    """Horizontal rule."""
    DEFAULT_CSS = "_Separator { height: 1; color: #2d2d4e; padding: 0 2; }"

    def render(self) -> str:
        return "─" * 76


class _CommandFooter(Static):
    """Bottom key-hint bar."""
    DEFAULT_CSS = "_CommandFooter { height: 1; background: #12122a; color: #555577; padding: 0 2; }"

    def render(self) -> str:
        return "commands:  : palette   p projects   s sessions   t tools   u suggest   l leaderboard   m team   $ plan   c chart   x export   / filter   r reload   ? help   q quit"


class DashboardScreen(Screen):
    """The default full-screen dashboard."""

    BINDINGS = [
        Binding("1", "set_range('1')", "1d", show=False),
        Binding("2", "set_range('2')", "7d", show=False),
        Binding("3", "set_range('3')", "30d", show=False),

        Binding(":", "command_palette", "palette", show=False),
        Binding("$", "set_plan",       "plan",    show=False),
        Binding("p", "drill_projects", "projects", show=False),
        Binding("s", "drill_sessions", "sessions", show=False),
        Binding("t", "drill_tools", "tools", show=False),
        Binding("e", "edit_categories", "edit rules", show=False),
        Binding("u", "suggest_categories", "suggest", show=False),
        Binding("l", "leaderboard", "leaderboard", show=False),
        Binding("m", "team",        "team",        show=False),
        Binding("x", "export_csv", "export", show=False),
        Binding("/", "filter_prompt", "filter", show=False),
        Binding("c", "toggle_chart", "chart", show=False),
        Binding("r", "reload", "reload", show=False),
        Binding("?", "help_overlay", "help", show=False),
        Binding("q", "app.quit", "quit", show=False),
    ]

    def __init__(self, store: Store, range_days: int = 7) -> None:
        super().__init__()
        self._store = store
        self._range_days = range_days
        self._filter: str = ""
        self._data: DashboardData | None = None
        self._last_sync: float = time.time()
        self._stacked: bool = False

    # ------------------------------------------------------------------
    # Compose
    # ------------------------------------------------------------------

    def compose(self) -> ComposeResult:
        yield _Header(range_days=self._range_days, id="dash-header")
        yield LiveStrip(id="live-strip")
        yield _Separator()
        yield RangeRow(range_days=self._range_days, id="range-row")
        yield TotalsPanel(id="totals")
        yield DailyPanel(id="daily")
        yield _Separator()
        with Horizontal(classes="two-col"):
            yield ProjectBarsPanel(id="project-bars")
            yield ModelBarsPanel(id="model-bars")
        with Horizontal(classes="two-col"):
            yield CategoryBarsPanel(id="category-bars")
            yield TaskBreakdownPanel(id="task-breakdown")
        yield _Separator()
        yield TimeOfDayPanel(id="time-of-day")
        yield SubagentStatsPanel(id="subagent-stats")
        yield TimingPanel(id="timing")
        yield _Separator()
        yield _CommandFooter()

    def on_mount(self) -> None:
        ensure_user_categories()
        self._refresh_data()
        self.set_interval(LIVE_REFRESH_SECONDS, self._tick_live)
        self.set_interval(1.0, self._tick_header)

    # ------------------------------------------------------------------
    # Refresh helpers
    # ------------------------------------------------------------------

    def _refresh_data(self) -> None:
        rules = load_rules()
        agg = Aggregator(self._store)
        self._data = agg.build(self._range_days, category_rules=rules)
        self._last_sync = time.time()
        self._update_all_panels()

    def _tick_live(self) -> None:
        self._store.sync()
        sessions = get_live_sessions(self._store)
        self.query_one("#live-strip", LiveStrip).update(sessions)

    def _tick_header(self) -> None:
        self.query_one("#dash-header", _Header).update(self._range_days, self._last_sync)

    def _update_all_panels(self) -> None:
        if not self._data:
            return
        d = self._data
        self.query_one("#dash-header", _Header).update(self._range_days, self._last_sync)
        self.query_one("#range-row", RangeRow).update(self._range_days)
        from ccspy import plan as _plan
        self.query_one("#totals", TotalsPanel).update(
            d.totals, d.prev_totals,
            range_days=self._range_days,
            plan_name=_plan.get_plan_name(),
            plan_monthly_cost=_plan.get_monthly_cost(),
        )
        self.query_one("#daily", DailyPanel).update(d.daily)
        self.query_one("#project-bars", ProjectBarsPanel).update(d.by_project, self._filter)
        self.query_one("#model-bars", ModelBarsPanel).update(d.by_model)
        self.query_one("#category-bars", CategoryBarsPanel).update(d.by_category)
        # Reapply chart mode so stacked indicator survives a reload
        if self._stacked:
            self.query_one("#project-bars",  ProjectBarsPanel).set_mode(True)
            self.query_one("#model-bars",     ModelBarsPanel).set_mode(True)
            self.query_one("#category-bars",  CategoryBarsPanel).set_mode(True)
        self.query_one("#task-breakdown", TaskBreakdownPanel).update(d.task_stats)
        self.query_one("#time-of-day", TimeOfDayPanel).update(d.by_hour)
        self.query_one("#subagent-stats", SubagentStatsPanel).update(d.subagents)
        self.query_one("#timing", TimingPanel).update(d.timing)

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------

    def action_toggle_chart(self) -> None:
        self._stacked = not self._stacked
        self.query_one("#project-bars", ProjectBarsPanel).set_mode(self._stacked)
        self.query_one("#model-bars",   ModelBarsPanel).set_mode(self._stacked)
        self.query_one("#category-bars", CategoryBarsPanel).set_mode(self._stacked)

    def action_set_range(self, key: str) -> None:
        self._range_days = {"1": 0, "2": 7, "3": 30}[key]
        self._refresh_data()

    def action_reload(self) -> None:
        self._store.sync()
        self._refresh_data()

    def action_edit_categories(self) -> None:
        editor = default_editor()
        with self.app.suspend():
            subprocess.run([editor, str(CONFIG_CATEGORIES)])
        self._refresh_data()

    def action_command_palette(self) -> None:
        from ccspy.ui.palette import CommandPaletteScreen

        def _dispatch(result: tuple | None) -> None:
            if result is None:
                return
            key, param = result
            if key == "range":
                self._range_days = int(param)
                self._refresh_data()
            elif key == "projects":
                self.action_drill_projects()
            elif key == "sessions":
                self.action_drill_sessions()
            elif key == "tools":
                self.action_drill_tools()
            elif key == "edit_categories":
                self.action_edit_categories()
            elif key == "export_csv":
                self.action_export_csv()
            elif key == "reload":
                self.action_reload()
            elif key == "plan":
                self.action_set_plan()
            elif key == "pricing":
                from ccspy.ui.drill import PricingTableScreen
                self.app.push_screen(PricingTableScreen())
            elif key == "sources":
                from ccspy.ui.drill import DataSourcesScreen
                self.app.push_screen(DataSourcesScreen(store=self._store))
            elif key == "help":
                self.action_help_overlay()

        self.app.push_screen(CommandPaletteScreen(store=self._store, data=self._data), _dispatch)

    def action_drill_projects(self) -> None:
        from ccspy.ui.drill import ProjectPickerScreen
        self.app.push_screen(ProjectPickerScreen(store=self._store, data=self._data))

    def action_drill_sessions(self) -> None:
        from ccspy.ui.drill import SessionPickerScreen
        self.app.push_screen(SessionPickerScreen(store=self._store, range_days=self._range_days))

    def action_drill_tools(self) -> None:
        from ccspy.ui.drill import ToolPickerScreen
        self.app.push_screen(ToolPickerScreen(store=self._store, data=self._data))

    def action_export_csv(self) -> None:
        from datetime import date
        agg = Aggregator(self._store)
        data = agg.export(days=self._range_days, fmt="csv")
        out = Path(f"~/ccspy-export-{date.today().strftime('%Y%m%d')}.csv").expanduser()
        out.write_text(data, encoding="utf-8")
        self.notify(f"Exported to {out}", title="ccspy export")

    def action_filter_prompt(self) -> None:
        from ccspy.ui.filter_modal import FilterModal
        self.app.push_screen(FilterModal(current=self._filter), self._apply_filter)

    def _apply_filter(self, text: str | None) -> None:
        if text is not None:
            self._filter = text
            if self._data:
                self.query_one("#project-bars", ProjectBarsPanel).update(
                    self._data.by_project, filter_text=self._filter
                )


    def action_suggest_categories(self) -> None:
        from ccspy.suggest import get_uncategorised_texts, analyse
        from ccspy.ui.suggest_screen import SuggestScreen
        from ccspy.categories import load_rules, USER_CATEGORIES_PATH

        existing_rules = load_rules()
        # Analyse all-time uncategorised sessions — category assignment is not range-dependent
        texts, tokens = get_uncategorised_texts(self._store, "1970-01-01", existing_rules)
        suggestions = analyse(texts)

        def _on_accept(n: int) -> None:
            if n:
                self.notify(f"Added {n} category rule{'s' if n != 1 else ''}", title="ccspy")
            self._refresh_data()

        self.app.push_screen(
            SuggestScreen(
                rules=suggestions,
                uncategorised_count=len(texts),
                uncategorised_tokens=tokens,
                categories_path=USER_CATEGORIES_PATH,
                existing_rules=existing_rules,
                on_accept=_on_accept,
            )
        )

    def action_set_plan(self) -> None:
        from ccspy.ui.plan_modal import PlanModal
        from ccspy import plan as _plan
        self.app.push_screen(
            PlanModal(current_name=_plan.get_plan_name()),
            self._handle_plan,
        )

    def _handle_plan(self, result: tuple[str, float] | None) -> None:
        if result is None:
            return
        name, cost = result
        from ccspy import plan as _plan
        _plan.set_plan(name, cost)
        self.notify(f"Plan set to {name} (${cost:.0f}/mo)", title="ccspy plan")
        self._refresh_data()

    def action_leaderboard(self) -> None:
        from ccspy.ui.leaderboard_screen import LeaderboardScreen
        self.app.push_screen(LeaderboardScreen(store=self._store))

    def action_team(self) -> None:
        from ccspy.ui.team_screen import TeamScreen
        self.app.push_screen(TeamScreen(store=self._store))

    def action_help_overlay(self) -> None:
        from ccspy.ui.help_modal import HelpModal
        self.app.push_screen(HelpModal())
