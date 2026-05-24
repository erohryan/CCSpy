"""Drill-down screens for projects, sessions, tools, pricing, and data sources."""
from __future__ import annotations

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import ScrollableContainer
from textual.screen import Screen
from textual.widgets import DataTable, Label, Static

from ccspy.store import Store
from ccspy.ui.widgets._format import fmt_tokens, fmt_cost, fmt_pct, fmt_duration, short_model

_BACK = [Binding("escape", "app.pop_screen", "Back", show=False)]

_BASE_CSS = """
background: #0d0d1a;
"""


class _DrillHeader(Static):
    DEFAULT_CSS = "_DrillHeader { height: 1; background: #12122a; color: #7a7a9a; padding: 0 2; }"


# ---------------------------------------------------------------------------
# Project picker
# ---------------------------------------------------------------------------

class ProjectPickerScreen(Screen):
    """All projects sorted by token usage — Enter to drill in."""

    BINDINGS = _BACK

    DEFAULT_CSS = "ProjectPickerScreen { background: #0d0d1a; } ProjectPickerScreen DataTable { height: 1fr; }"

    def __init__(self, store: Store, data) -> None:
        super().__init__()
        self._store = store
        self._projects = data.by_project if data else []

    def compose(self) -> ComposeResult:
        yield _DrillHeader("p  Projects   Enter drill-down   Esc back")
        yield DataTable(id="proj-table", cursor_type="row", zebra_stripes=True)

    def on_mount(self) -> None:
        dt = self.query_one("#proj-table", DataTable)
        dt.add_columns("#", "Project", "Tokens", "api-equiv $", "Sessions", "%")
        for i, p in enumerate(self._projects):
            dt.add_row(
                str(i + 1),
                p.project_name[:42],
                fmt_tokens(p.total_tokens),
                fmt_cost(p.est_api_cost_usd),
                str(p.session_count),
                fmt_pct(p.pct).strip(),
                key=p.project_name,
            )
        dt.focus()

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        project_name = str(event.row_key.value)
        self.app.push_screen(ProjectOverviewScreen(store=self._store, project_name=project_name))


# ---------------------------------------------------------------------------
# Project overview (metrics + day utilization chart)
# ---------------------------------------------------------------------------

class ProjectOverviewScreen(Screen):
    """Key metrics and day-by-day utilization chart for one project."""

    BINDINGS = [
        Binding("escape", "app.pop_screen", "Back", show=False),
        Binding("enter", "daily_detail", "daily detail", show=False),
        Binding("d", "daily_detail", "daily detail", show=False),
        Binding("s", "all_sessions", "sessions", show=False),
    ]

    DEFAULT_CSS = """
    ProjectOverviewScreen { background: #0d0d1a; }
    ProjectOverviewScreen ScrollableContainer { height: 1fr; }
    """

    def __init__(self, store: Store, project_name: str) -> None:
        super().__init__()
        self._store = store
        self._project_name = project_name

    def compose(self) -> ComposeResult:
        yield _DrillHeader(
            f"proj  {self._project_name}   Enter/d → daily table   s → sessions   Esc back"
        )
        yield ScrollableContainer(Static("", id="overview-body"))

    def on_mount(self) -> None:
        from ccspy.pricing import compute_cost
        from rich.text import Text

        token_rows = self._store.query(
            """
            SELECT
              substr(datetime(t.ts, 'localtime'), 1, 10) as day,
              t.model,
              SUM(t.input_tokens)             as inp,
              SUM(t.output_tokens)            as out,
              SUM(t.cache_creation_tokens)    as cc,
              SUM(t.cache_read_tokens)        as cr,
              SUM(t.cache_creation_1h_tokens) as cc1h,
              SUM(t.cache_creation_5m_tokens) as cc5m
            FROM turns t
            JOIN sessions s ON t.session_id = s.session_id
            WHERE s.project_name = ?
            GROUP BY day, t.model
            ORDER BY day DESC
            """,
            (self._project_name,),
        )
        sess_rows = self._store.query(
            """
            SELECT substr(datetime(t.ts, 'localtime'), 1, 10) as day,
                   COUNT(DISTINCT t.session_id) as sess_count
            FROM turns t
            JOIN sessions s ON t.session_id = s.session_id
            WHERE s.project_name = ?
            GROUP BY day
            """,
            (self._project_name,),
        )
        sess_by_day = {r["day"]: r["sess_count"] or 0 for r in sess_rows}

        build_rows = self._store.query(
            """
            SELECT
              substr(datetime(t.ts, 'localtime'), 1, 10) as day,
              SUM(CASE
                WHEN t.user_msg_ts != '' AND t.user_msg_ts < t.ts
                 AND (JULIANDAY(t.ts) - JULIANDAY(t.user_msg_ts)) * 86400 BETWEEN 0.5 AND 600
                THEN (JULIANDAY(t.ts) - JULIANDAY(t.user_msg_ts)) * 86400
                ELSE 0 END) as build_secs
            FROM turns t
            JOIN sessions s ON t.session_id = s.session_id
            WHERE s.project_name = ?
            GROUP BY day
            """,
            (self._project_name,),
        )
        build_by_day = {r["day"]: r["build_secs"] or 0.0 for r in build_rows}

        days: dict[str, dict] = {}
        costs_by_day: dict[str, list] = {}
        total_inp = total_out = total_cc = total_cr = 0

        for r in token_rows:
            day = r["day"]
            if day not in days:
                days[day] = {"inp": 0, "out": 0, "cc": 0, "cr": 0}
                costs_by_day[day] = []
            d = days[day]
            inp, out, cc, cr = r["inp"] or 0, r["out"] or 0, r["cc"] or 0, r["cr"] or 0
            d["inp"] += inp; d["out"] += out; d["cc"] += cc; d["cr"] += cr
            total_inp += inp; total_out += out; total_cc += cc; total_cr += cr
            cost = compute_cost(
                r["model"],
                input_tokens=inp, output_tokens=out,
                cache_creation_tokens=cc, cache_read_tokens=cr,
                cache_creation_1h_tokens=r["cc1h"] or 0,
                cache_creation_5m_tokens=r["cc5m"] or 0,
            )
            costs_by_day[day].append(cost)

        def _sum(costs):
            known = [c for c in costs if c is not None]
            return round(sum(known), 6) if known else None

        total_tokens = total_inp + total_out + total_cc + total_cr
        total_cost   = _sum([c for cs in costs_by_day.values() for c in cs])
        total_build  = sum(build_by_day.values())
        days_worked  = len(days)
        total_sess   = sum(sess_by_day.values())

        avg_session_cost  = (total_cost / total_sess) if total_cost and total_sess > 0 else None
        avg_day_tokens    = total_tokens // days_worked if days_worked else 0
        avg_build_per_sess = total_build / total_sess if total_sess > 0 else 0.0

        t = Text()

        # ── Headline metrics ──────────────────────────────────────────────
        t.append("\n")
        t.append(f"  {days_worked}", style="bold white")
        t.append(" days worked  ·  ", style="dim")
        t.append(f"{total_sess}", style="bold white")
        t.append(" sessions  ·  ", style="dim")
        t.append(fmt_tokens(total_tokens), style="bold #9999cc")
        t.append(" tokens  ·  ", style="dim")
        t.append(fmt_cost(total_cost), style="bold #44cf6c")
        t.append(" api-equiv  ·  ", style="dim")
        t.append(fmt_duration(total_build) if total_build > 1 else "—", style="bold #cc9944")
        t.append(" building\n", style="dim")

        t.append("  avg/session  ", style="dim")
        t.append(fmt_cost(avg_session_cost), style="#44cf6c")
        t.append("  ·  avg/day  ", style="dim")
        t.append(fmt_tokens(avg_day_tokens), style="#9999cc")
        t.append("  ·  avg build/session  ", style="dim")
        t.append(fmt_duration(avg_build_per_sess) if avg_build_per_sess > 1 else "—", style="#cc9944")
        t.append("\n")

        # ── Day utilization bar chart ─────────────────────────────────────
        BAR_WIDTH = 30
        t.append("\n  DAILY TOKEN USAGE\n", style="bold #7a7a9a")
        t.append("  " + "─" * 68 + "\n", style="dim #2d2d4e")

        max_day_tok = max(
            (d["inp"] + d["out"] + d["cc"] + d["cr"] for d in days.values()),
            default=1,
        ) or 1

        for day in sorted(days.keys(), reverse=True):
            d = days[day]
            day_tok   = d["inp"] + d["out"] + d["cc"] + d["cr"]
            day_cost  = _sum(costs_by_day[day])
            build     = build_by_day.get(day, 0.0)
            filled    = max(1, round(day_tok / max_day_tok * BAR_WIDTH))
            empty     = BAR_WIDTH - filled

            t.append(f"  {day}  ", style="dim")
            t.append("█" * filled, style="#4455cc")
            t.append("░" * empty, style="dim #2d2d4e")
            t.append(f"  {fmt_tokens(day_tok):>6}", style="white")
            t.append(f"  {fmt_cost(day_cost):>7}", style="#44cf6c")
            build_str = fmt_duration(build) if build > 1 else "—"
            t.append(f"  {build_str:>7}", style="#cc9944")
            t.append(f"  {sess_by_day.get(day, 0)} sess\n", style="dim")

        # ── Token type breakdown ──────────────────────────────────────────
        BREAK_WIDTH = 24
        t.append("\n  TOKEN BREAKDOWN\n", style="bold #7a7a9a")
        t.append("  " + "─" * 68 + "\n", style="dim #2d2d4e")

        breakdown = [
            ("Input   ", total_inp,  "#6677cc"),
            ("Output  ", total_out,  "#44cf6c"),
            ("Cache-R ", total_cr,   "#cc9944"),
            ("Cache-W ", total_cc,   "#996633"),
        ]
        for label, val, color in breakdown:
            pct    = val / total_tokens * 100 if total_tokens else 0.0
            filled = max(0, round(pct / 100 * BREAK_WIDTH))
            empty  = BREAK_WIDTH - filled
            t.append(f"  {label}", style="dim")
            t.append(f"{fmt_tokens(val):>6}", style="white")
            t.append(f"  {pct:4.0f}%  ", style="dim")
            t.append("█" * filled, style=color)
            t.append("░" * empty, style="dim #2d2d4e")
            t.append("\n")

        t.append("\n")
        self.query_one("#overview-body", Static).update(t)

    def action_daily_detail(self) -> None:
        self.app.push_screen(
            ProjectDetailScreen(store=self._store, project_name=self._project_name)
        )

    def action_all_sessions(self) -> None:
        self.app.push_screen(
            ProjectDrillScreen(store=self._store, project_name=self._project_name)
        )


# ---------------------------------------------------------------------------
# Project detail (per-day breakdown)
# ---------------------------------------------------------------------------

class ProjectDetailScreen(Screen):
    """Per-day token, cost, and build-time breakdown for one project."""

    BINDINGS = [
        Binding("escape", "app.pop_screen", "Back", show=False),
        Binding("s", "all_sessions", "all sessions", show=False),
    ]

    DEFAULT_CSS = """
    ProjectDetailScreen { background: #0d0d1a; }
    ProjectDetailScreen DataTable { height: 1fr; }
    ProjectDetailScreen Label { color: #7a7a9a; padding: 0 2; height: 1; }
    """

    def __init__(self, store: Store, project_name: str) -> None:
        super().__init__()
        self._store = store
        self._project_name = project_name

    def compose(self) -> ComposeResult:
        yield _DrillHeader(
            f"proj  {self._project_name}   Enter → day sessions   s → all sessions   Esc back"
        )
        yield Label("", id="proj-totals")
        yield DataTable(id="proj-day-table", cursor_type="row", zebra_stripes=True)

    def on_mount(self) -> None:
        from ccspy.pricing import compute_cost

        # Per-(day, model) token counts — needed to compute cost accurately
        token_rows = self._store.query(
            """
            SELECT
              substr(datetime(t.ts, 'localtime'), 1, 10) as day,
              t.model,
              SUM(t.input_tokens)               as inp,
              SUM(t.output_tokens)              as out,
              SUM(t.cache_creation_tokens)      as cc,
              SUM(t.cache_read_tokens)          as cr,
              SUM(t.cache_creation_1h_tokens)   as cc1h,
              SUM(t.cache_creation_5m_tokens)   as cc5m
            FROM turns t
            JOIN sessions s ON t.session_id = s.session_id
            WHERE s.project_name = ?
            GROUP BY day, t.model
            ORDER BY day DESC
            """,
            (self._project_name,),
        )

        # Distinct sessions per day
        sess_rows = self._store.query(
            """
            SELECT
              substr(datetime(t.ts, 'localtime'), 1, 10) as day,
              COUNT(DISTINCT t.session_id) as sess_count
            FROM turns t
            JOIN sessions s ON t.session_id = s.session_id
            WHERE s.project_name = ?
            GROUP BY day
            """,
            (self._project_name,),
        )
        sess_by_day = {r["day"]: r["sess_count"] or 0 for r in sess_rows}

        # Build time per day (0.5–600 s window per turn, same cap as global timing)
        build_rows = self._store.query(
            """
            SELECT
              substr(datetime(t.ts, 'localtime'), 1, 10) as day,
              SUM(CASE
                WHEN t.user_msg_ts != '' AND t.user_msg_ts < t.ts
                 AND (JULIANDAY(t.ts) - JULIANDAY(t.user_msg_ts)) * 86400 BETWEEN 0.5 AND 600
                THEN (JULIANDAY(t.ts) - JULIANDAY(t.user_msg_ts)) * 86400
                ELSE 0 END) as build_secs
            FROM turns t
            JOIN sessions s ON t.session_id = s.session_id
            WHERE s.project_name = ?
            GROUP BY day
            """,
            (self._project_name,),
        )
        build_by_day = {r["day"]: r["build_secs"] or 0.0 for r in build_rows}

        # Merge token rows into per-day totals
        days: dict[str, dict] = {}
        costs_by_day: dict[str, list] = {}
        for r in token_rows:
            day = r["day"]
            if day not in days:
                days[day] = {"inp": 0, "out": 0, "cc": 0, "cr": 0}
                costs_by_day[day] = []
            d = days[day]
            inp, out, cc, cr = r["inp"] or 0, r["out"] or 0, r["cc"] or 0, r["cr"] or 0
            d["inp"] += inp; d["out"] += out; d["cc"] += cc; d["cr"] += cr
            cost = compute_cost(
                r["model"],
                input_tokens=inp, output_tokens=out,
                cache_creation_tokens=cc, cache_read_tokens=cr,
                cache_creation_1h_tokens=r["cc1h"] or 0,
                cache_creation_5m_tokens=r["cc5m"] or 0,
            )
            costs_by_day[day].append(cost)

        def _sum(costs):
            known = [c for c in costs if c is not None]
            return round(sum(known), 6) if known else None

        # Summary totals
        total_inp = sum(d["inp"] for d in days.values())
        total_out = sum(d["out"] for d in days.values())
        total_cc  = sum(d["cc"]  for d in days.values())
        total_cr  = sum(d["cr"]  for d in days.values())
        total_tokens = total_inp + total_out + total_cc + total_cr
        total_cost   = _sum([c for cs in costs_by_day.values() for c in cs])
        total_build  = sum(build_by_day.values())
        days_worked  = len(days)
        total_sess   = sum(sess_by_day.values())

        self.query_one("#proj-totals", Label).update(
            f"  {days_worked} days worked · {total_sess} sessions · "
            f"{fmt_tokens(total_tokens)} tokens · {fmt_cost(total_cost)} api-equiv · "
            f"{fmt_duration(total_build)} building"
        )

        dt = self.query_one("#proj-day-table", DataTable)
        dt.add_columns("Date", "Sess", "Tokens", "In", "Out", "Cache", "Cost", "Build")
        for day in sorted(days.keys(), reverse=True):
            d = days[day]
            total = d["inp"] + d["out"] + d["cc"] + d["cr"]
            cache = d["cc"] + d["cr"]
            cost  = _sum(costs_by_day[day])
            build = build_by_day.get(day, 0.0)
            dt.add_row(
                day,
                str(sess_by_day.get(day, 0)),
                fmt_tokens(total),
                fmt_tokens(d["inp"]),
                fmt_tokens(d["out"]),
                fmt_tokens(cache),
                fmt_cost(cost),
                fmt_duration(build) if build > 1 else "—",
                key=day,
            )
        dt.focus()

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        day = str(event.row_key.value)
        self.app.push_screen(
            ProjectDrillScreen(store=self._store, project_name=self._project_name, date=day)
        )

    def action_all_sessions(self) -> None:
        self.app.push_screen(
            ProjectDrillScreen(store=self._store, project_name=self._project_name)
        )


# ---------------------------------------------------------------------------
# Project drill (session list)
# ---------------------------------------------------------------------------

class ProjectDrillScreen(Screen):
    """Sessions for a single project, optionally filtered to a specific date."""

    BINDINGS = _BACK

    DEFAULT_CSS = "ProjectDrillScreen { background: #0d0d1a; } ProjectDrillScreen DataTable { height: 1fr; }"

    def __init__(self, store: Store, project_name: str, date: str | None = None) -> None:
        super().__init__()
        self._store = store
        self._project_name = project_name
        self._date = date

    def compose(self) -> ComposeResult:
        suffix = f"  ({self._date})" if self._date else ""
        yield _DrillHeader(f"p  {self._project_name}{suffix}   Enter session detail   Esc back")
        yield DataTable(id="proj-sess-table", cursor_type="row", zebra_stripes=True)

    def on_mount(self) -> None:
        if self._date:
            rows = self._store.query(
                """
                SELECT s.session_id, s.started_at, s.first_user_text, s.is_sidechain,
                  COALESCE(SUM(t.input_tokens + t.output_tokens +
                              t.cache_creation_tokens + t.cache_read_tokens), 0) as total_tokens,
                  GROUP_CONCAT(DISTINCT t.model) as models
                FROM sessions s
                LEFT JOIN turns t ON s.session_id = t.session_id
                WHERE s.project_name = ?
                  AND substr(datetime(s.started_at, 'localtime'), 1, 10) = ?
                GROUP BY s.session_id
                ORDER BY s.started_at DESC
                """,
                (self._project_name, self._date),
            )
        else:
            rows = self._store.query(
                """
                SELECT s.session_id, s.started_at, s.first_user_text, s.is_sidechain,
                  COALESCE(SUM(t.input_tokens + t.output_tokens +
                              t.cache_creation_tokens + t.cache_read_tokens), 0) as total_tokens,
                  GROUP_CONCAT(DISTINCT t.model) as models
                FROM sessions s
                LEFT JOIN turns t ON s.session_id = t.session_id
                WHERE s.project_name = ?
                GROUP BY s.session_id
                ORDER BY s.started_at DESC
                LIMIT 100
                """,
                (self._project_name,),
            )

        dt = self.query_one("#proj-sess-table", DataTable)
        dt.add_columns("Date", "Time", "First message", "Tokens", "Model(s)", "Type")
        for r in rows:
            started = r["started_at"] or ""
            models_str = ", ".join(
                short_model(m) for m in (r["models"] or "").split(",") if m
            )
            kind = "subagent" if r["is_sidechain"] else "main"
            dt.add_row(
                started[:10],
                started[11:16],
                (r["first_user_text"] or "—")[:48],
                fmt_tokens(r["total_tokens"]),
                models_str or "—",
                kind,
                key=r["session_id"],
            )
        dt.focus()

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        session_id = str(event.row_key.value)
        self.app.push_screen(SessionDrillScreen(store=self._store, session_id=session_id))


# ---------------------------------------------------------------------------
# Session picker
# ---------------------------------------------------------------------------

class SessionPickerScreen(Screen):
    """Recent sessions across all projects — Enter for turn detail."""

    BINDINGS = _BACK

    DEFAULT_CSS = "SessionPickerScreen { background: #0d0d1a; } SessionPickerScreen DataTable { height: 1fr; }"

    def __init__(self, store: Store, range_days: int = 7) -> None:
        super().__init__()
        self._store = store
        self._range_days = range_days

    def compose(self) -> ComposeResult:
        yield _DrillHeader(f"s  Sessions ({self._range_days}d, last 50)   Enter detail   Esc back")
        yield DataTable(id="sess-pick-table", cursor_type="row", zebra_stripes=True)

    def on_mount(self) -> None:
        from ccspy.aggregator import _since_ts
        since = _since_ts(self._range_days)
        rows = self._store.query(
            """
            SELECT s.session_id, s.project_name, s.started_at, s.first_user_text,
              COALESCE(SUM(t.input_tokens + t.output_tokens +
                          t.cache_creation_tokens + t.cache_read_tokens), 0) as total_tokens
            FROM sessions s
            LEFT JOIN turns t ON s.session_id = t.session_id
            WHERE s.started_at >= ?
            GROUP BY s.session_id
            ORDER BY s.started_at DESC
            LIMIT 50
            """,
            (since,),
        )

        dt = self.query_one("#sess-pick-table", DataTable)
        dt.add_columns("Date", "Time", "Project", "First message", "Tokens")
        for r in rows:
            started = r["started_at"] or ""
            dt.add_row(
                started[:10],
                started[11:16],
                (r["project_name"] or "")[:26],
                (r["first_user_text"] or "—")[:46],
                fmt_tokens(r["total_tokens"]),
                key=r["session_id"],
            )
        dt.focus()

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        session_id = str(event.row_key.value)
        self.app.push_screen(SessionDrillScreen(store=self._store, session_id=session_id))


# ---------------------------------------------------------------------------
# Session drill
# ---------------------------------------------------------------------------

class SessionDrillScreen(Screen):
    """All turns within a single session."""

    BINDINGS = _BACK

    DEFAULT_CSS = """
    SessionDrillScreen { background: #0d0d1a; }
    SessionDrillScreen DataTable { height: 1fr; }
    SessionDrillScreen Label { color: #7a7a9a; padding: 0 2; height: 1; }
    """

    def __init__(self, store: Store, session_id: str) -> None:
        super().__init__()
        self._store = store
        self._session_id = session_id

    def compose(self) -> ComposeResult:
        yield _DrillHeader("s  Session turns   Esc back")
        yield Label("", id="sess-meta")
        yield DataTable(id="turns-table", cursor_type="row", zebra_stripes=True)

    def on_mount(self) -> None:
        sess_rows = self._store.query(
            "SELECT project_name, started_at, first_user_text FROM sessions WHERE session_id = ?",
            (self._session_id,),
        )
        if sess_rows:
            s = sess_rows[0]
            meta = f"  {s['project_name']}  {(s['started_at'] or '')[:16]}  {(s['first_user_text'] or '')[:72]}"
            self.query_one("#sess-meta", Label).update(meta)

        turn_rows = self._store.query(
            """
            SELECT t.turn_id, t.ts, t.model,
              t.input_tokens, t.output_tokens,
              t.cache_creation_tokens, t.cache_read_tokens,
              GROUP_CONCAT(tc.tool_name) as tools
            FROM turns t
            LEFT JOIN tool_calls tc ON tc.turn_id = t.turn_id
            WHERE t.session_id = ?
            GROUP BY t.turn_id
            ORDER BY t.ts
            """,
            (self._session_id,),
        )

        dt = self.query_one("#turns-table", DataTable)
        dt.add_columns("Time", "Model", "Total", "In", "Out", "CacheW", "CacheR", "Tools")
        for r in turn_rows:
            total = (
                (r["input_tokens"] or 0)
                + (r["output_tokens"] or 0)
                + (r["cache_creation_tokens"] or 0)
                + (r["cache_read_tokens"] or 0)
            )
            tools_raw = r["tools"] or ""
            tools_list = sorted(set(t for t in tools_raw.split(",") if t))
            tools_str = ", ".join(tools_list[:3])
            if len(tools_list) > 3:
                tools_str += f" +{len(tools_list) - 3}"
            dt.add_row(
                (r["ts"] or "")[11:16],
                short_model(r["model"] or ""),
                fmt_tokens(total),
                fmt_tokens(r["input_tokens"] or 0),
                fmt_tokens(r["output_tokens"] or 0),
                fmt_tokens(r["cache_creation_tokens"] or 0),
                fmt_tokens(r["cache_read_tokens"] or 0),
                tools_str or "—",
            )
        dt.focus()


# ---------------------------------------------------------------------------
# Tool picker
# ---------------------------------------------------------------------------

class ToolPickerScreen(Screen):
    """All tools sorted by call count — Enter to see per-project breakdown."""

    BINDINGS = _BACK

    DEFAULT_CSS = "ToolPickerScreen { background: #0d0d1a; } ToolPickerScreen DataTable { height: 1fr; }"

    def __init__(self, store: Store, data) -> None:
        super().__init__()
        self._store = store
        self._tools = data.by_tool if data else []

    def compose(self) -> ComposeResult:
        yield _DrillHeader("t  Tools   Enter drill-down   Esc back")
        yield DataTable(id="tool-table", cursor_type="row", zebra_stripes=True)

    def on_mount(self) -> None:
        dt = self.query_one("#tool-table", DataTable)
        dt.add_columns("#", "Tool", "Calls", "%")
        for i, tool in enumerate(self._tools):
            dt.add_row(
                str(i + 1),
                tool.tool_name[:44],
                str(tool.call_count),
                fmt_pct(tool.pct).strip(),
                key=tool.tool_name,
            )
        dt.focus()

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        tool_name = str(event.row_key.value)
        self.app.push_screen(ToolDrillScreen(store=self._store, tool_name=tool_name))


# ---------------------------------------------------------------------------
# Tool drill
# ---------------------------------------------------------------------------

class ToolDrillScreen(Screen):
    """Top projects using a specific tool."""

    BINDINGS = _BACK

    DEFAULT_CSS = "ToolDrillScreen { background: #0d0d1a; } ToolDrillScreen DataTable { height: 1fr; }"

    def __init__(self, store: Store, tool_name: str) -> None:
        super().__init__()
        self._store = store
        self._tool_name = tool_name

    def compose(self) -> ComposeResult:
        yield _DrillHeader(f"t  {self._tool_name}   Esc back")
        yield DataTable(id="tool-drill-table", cursor_type="row", zebra_stripes=True)

    def on_mount(self) -> None:
        rows = self._store.query(
            """
            SELECT s.project_name, COUNT(*) as call_count,
              COUNT(DISTINCT t.session_id) as sessions
            FROM tool_calls tc
            JOIN turns t ON tc.turn_id = t.turn_id
            JOIN sessions s ON t.session_id = s.session_id
            WHERE tc.tool_name = ?
            GROUP BY s.project_name
            ORDER BY call_count DESC
            LIMIT 20
            """,
            (self._tool_name,),
        )

        dt = self.query_one("#tool-drill-table", DataTable)
        dt.add_columns("Project", "Calls", "Sessions")
        for r in rows:
            dt.add_row(
                (r["project_name"] or "")[:48],
                str(r["call_count"] or 0),
                str(r["sessions"] or 0),
            )
        dt.focus()


# ---------------------------------------------------------------------------
# Pricing table
# ---------------------------------------------------------------------------

class PricingTableScreen(Screen):
    """All model pricing rates (per 1M tokens, api-equiv)."""

    BINDINGS = _BACK

    DEFAULT_CSS = """
    PricingTableScreen { background: #0d0d1a; }
    PricingTableScreen DataTable { height: 1fr; }
    PricingTableScreen Label { color: #7a7a9a; padding: 0 2; height: 1; }
    """

    def compose(self) -> ComposeResult:
        yield _DrillHeader("Pricing table   (USD per 1M tokens, api-equiv)   Esc back")
        yield Label("", id="pricing-meta")
        yield DataTable(id="pricing-table", cursor_type="row", zebra_stripes=True)

    def on_mount(self) -> None:
        from ccspy.pricing import _load_table, pricing_updated

        self.query_one("#pricing-meta", Label).update(f"  Prices as of: {pricing_updated()}")

        table = _load_table()
        models = table.get("models", {})

        dt = self.query_one("#pricing-table", DataTable)
        dt.add_columns("Model", "Input", "Output", "Cache-W 5m", "Cache-W 1h", "Cache-R")

        for model_id, p in models.items():
            dt.add_row(
                short_model(model_id),
                f"${p.get('input_per_mtok', 0):.2f}",
                f"${p.get('output_per_mtok', 0):.2f}",
                f"${p.get('cache_write_5m_per_mtok', p.get('cache_write_per_mtok', 0)):.2f}",
                f"${p.get('cache_write_1h_per_mtok', 0):.2f}",
                f"${p.get('cache_read_per_mtok', 0):.2f}",
            )
        dt.focus()


# ---------------------------------------------------------------------------
# Data sources
# ---------------------------------------------------------------------------

class DataSourcesScreen(Screen):
    """Show JSONL file count, DB stats, and paths."""

    BINDINGS = _BACK

    DEFAULT_CSS = "DataSourcesScreen { background: #0d0d1a; } DataSourcesScreen Static { color: #7a7a9a; padding: 1 2; }"

    def __init__(self, store: Store) -> None:
        super().__init__()
        self._store = store

    def compose(self) -> ComposeResult:
        yield _DrillHeader("Data sources   Esc back")
        yield Static(id="sources-content")

    def on_mount(self) -> None:
        from ccspy.parser import discover_jsonl_files
        from rich.text import Text

        file_count = sum(1 for _ in discover_jsonl_files())
        session_count = self._store.query("SELECT COUNT(*) as c FROM sessions")[0]["c"] or 0
        turn_count = self._store.query("SELECT COUNT(*) as c FROM turns")[0]["c"] or 0
        tool_count = self._store.query("SELECT COUNT(*) as c FROM tool_calls")[0]["c"] or 0
        db_path = Store.db_path()

        t = Text()
        t.append("Data directory\n", style="bold white")
        t.append("  ~/.claude/projects/**/*.jsonl\n\n")
        t.append("JSONL files found\n", style="bold white")
        t.append(f"  {file_count}\n\n")
        t.append("Cache database\n", style="bold white")
        t.append(f"  {db_path}\n")
        t.append(f"  {session_count} sessions  ·  {turn_count} turns  ·  {tool_count} tool calls\n\n")
        t.append("Category rules\n", style="bold white")
        t.append("  ~/.config/ccspy/categories.toml\n\n")
        t.append("ccspy is read-only — it never modifies your Claude Code data.\n", style="dim")
        t.append("All $ figures are api-equiv estimates; Pro/Max users pay flat rate.\n", style="dim")

        self.query_one("#sources-content", Static).update(t)
