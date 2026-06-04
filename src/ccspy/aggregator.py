"""Pure aggregation functions over the Store.

All functions take a Store and date-range parameters and return plain dicts
or dataclasses — no Textual or UI concerns here.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Optional

from ccspy.store import Store


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _since_ts(days: int) -> str:
    """ISO timestamp for `days` ago. days=0 means midnight local time today."""
    if days == 0:
        import datetime as _dt
        local_now = _dt.datetime.now().astimezone()
        midnight = local_now.replace(hour=0, minute=0, second=0, microsecond=0)
        return midnight.astimezone(timezone.utc).isoformat()
    dt = _now_utc() - timedelta(days=days)
    return dt.isoformat()


# ---------------------------------------------------------------------------
# Result dataclasses
# ---------------------------------------------------------------------------


@dataclass
class RangeTotals:
    input_tokens: int = 0
    output_tokens: int = 0
    cache_creation_tokens: int = 0
    cache_read_tokens: int = 0
    total_tokens: int = 0
    est_api_cost_usd: Optional[float] = None
    session_count: int = 0
    project_count: int = 0


@dataclass
class DailyBucket:
    date: str  # YYYY-MM-DD
    total_tokens: int = 0
    est_api_cost_usd: Optional[float] = None


@dataclass
class ProjectStats:
    project_name: str
    total_tokens: int = 0
    session_count: int = 0
    pct: float = 0.0
    est_api_cost_usd: Optional[float] = None


@dataclass
class ModelStats:
    model: str
    total_tokens: int = 0
    pct: float = 0.0
    est_api_cost_usd: Optional[float] = None


@dataclass
class CategoryStats:
    category: str
    total_tokens: int = 0
    session_count: int = 0
    pct: float = 0.0


@dataclass
class ToolStats:
    tool_name: str
    call_count: int = 0
    pct: float = 0.0


@dataclass
class HourBucket:
    hour: int  # 0-23
    total_tokens: int = 0


@dataclass
class SubagentStats:
    total_spawned: int = 0
    avg_per_session: float = 0.0
    peak_concurrent: int = 0


@dataclass
class TimingStats:
    total_processing_secs: float = 0.0
    total_wait_secs: float = 0.0
    samples: int = 0


@dataclass
class ProjectTaskStats:
    project_name: str
    task_count: int = 0
    avg_duration_secs: float = 0.0
    total_tokens: int = 0
    plan_tokens: int = 0
    execute_tokens: int = 0

    @property
    def execute_pct(self) -> float:
        return (self.execute_tokens / self.total_tokens * 100) if self.total_tokens else 0.0


@dataclass
class DashboardData:
    range_days: int
    totals: RangeTotals = field(default_factory=RangeTotals)
    prev_totals: RangeTotals = field(default_factory=RangeTotals)
    daily: list[DailyBucket] = field(default_factory=list)
    by_project: list[ProjectStats] = field(default_factory=list)
    by_model: list[ModelStats] = field(default_factory=list)
    by_category: list[CategoryStats] = field(default_factory=list)
    by_tool: list[ToolStats] = field(default_factory=list)
    by_hour: list[HourBucket] = field(default_factory=list)
    subagents: SubagentStats = field(default_factory=SubagentStats)
    timing: TimingStats = field(default_factory=TimingStats)
    task_stats: list[ProjectTaskStats] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

_TOKEN_COLS = (
    "SUM(input_tokens) as inp, SUM(output_tokens) as out, "
    "SUM(cache_creation_tokens) as cc, SUM(cache_read_tokens) as cr, "
    "SUM(cache_creation_1h_tokens) as cc1h, SUM(cache_creation_5m_tokens) as cc5m"
)


def _row_cost(row, model: str, compute_cost) -> Optional[float]:
    return compute_cost(
        model,
        input_tokens=row["inp"] or 0,
        output_tokens=row["out"] or 0,
        cache_creation_tokens=row["cc"] or 0,
        cache_read_tokens=row["cr"] or 0,
        cache_creation_1h_tokens=row["cc1h"] or 0,
        cache_creation_5m_tokens=row["cc5m"] or 0,
    )


def _sum_cost(costs: list[Optional[float]]) -> Optional[float]:
    """Sum a list of costs; returns None only if ALL are None."""
    known = [c for c in costs if c is not None]
    return round(sum(known), 6) if known else None


def lifetime_project_costs(store: Store) -> dict[str, Optional[float]]:
    """All-time estimated API cost per project (no date filter)."""
    from ccspy.pricing import compute_cost
    rows = store.query(
        f"""
        SELECT s.project_name, t.model, {_TOKEN_COLS}
        FROM turns t
        JOIN sessions s ON t.session_id = s.session_id
        GROUP BY s.project_name, t.model
        """,
        (),
    )
    costs: dict[str, list[Optional[float]]] = {}
    for r in rows:
        name = r["project_name"]
        if name not in costs:
            costs[name] = []
        costs[name].append(_row_cost(r, r["model"], compute_cost))
    return {name: _sum_cost(cs) for name, cs in costs.items()}


# ---------------------------------------------------------------------------
# Aggregator
# ---------------------------------------------------------------------------


class Aggregator:
    """Builds DashboardData from a Store for a given date range."""

    def __init__(self, store: Store) -> None:
        self._store = store

    def build(self, days: int, category_rules: list[dict] | None = None) -> DashboardData:
        """Compute all dashboard panels for the given range."""
        from ccspy.pricing import compute_cost
        from ccspy.categories import categorise

        since = _since_ts(days)
        # For today (days=0): previous period = yesterday midnight → today midnight
        prev_since = _since_ts(1) if days == 0 else _since_ts(days * 2)

        data = DashboardData(range_days=days)
        data.totals = self._totals(since, compute_cost)
        data.prev_totals = self._totals(prev_since, compute_cost, until=since)
        data.daily = self._daily(since, compute_cost)
        data.by_project = self._by_project(since, compute_cost)
        data.by_model = self._by_model(since, compute_cost)
        data.by_tool = self._by_tool(since)
        data.by_hour = self._by_hour(since)
        data.subagents = self._subagents(since)
        data.timing = self._timing_stats(since)
        data.task_stats = self._task_stats_by_project(since)

        if category_rules:
            data.by_category = self._by_category(since, category_rules, categorise)

        return data

    # ------------------------------------------------------------------
    # Panel builders
    # ------------------------------------------------------------------

    def _totals(self, since: str, compute_cost, until: str | None = None) -> RangeTotals:
        if until:
            model_rows = self._store.query(
                f"SELECT model, {_TOKEN_COLS} FROM turns WHERE ts >= ? AND ts < ? GROUP BY model",
                (since, until),
            )
            count_rows = self._store.query(
                "SELECT COUNT(DISTINCT session_id) as sessions FROM turns WHERE ts >= ? AND ts < ?",
                (since, until),
            )
            proj_count = self._store.query(
                "SELECT COUNT(DISTINCT project_name) as c FROM sessions WHERE started_at >= ? AND started_at < ?",
                (since, until),
            )[0]["c"] or 0
        else:
            model_rows = self._store.query(
                f"SELECT model, {_TOKEN_COLS} FROM turns WHERE ts >= ? GROUP BY model",
                (since,),
            )
            count_rows = self._store.query(
                "SELECT COUNT(DISTINCT session_id) as sessions FROM turns WHERE ts >= ?",
                (since,),
            )
            proj_count = self._store.query(
                "SELECT COUNT(DISTINCT project_name) as c FROM sessions WHERE started_at >= ?",
                (since,),
            )[0]["c"] or 0

        inp = sum(r["inp"] or 0 for r in model_rows)
        out = sum(r["out"] or 0 for r in model_rows)
        cc = sum(r["cc"] or 0 for r in model_rows)
        cr = sum(r["cr"] or 0 for r in model_rows)
        costs = [_row_cost(r, r["model"], compute_cost) for r in model_rows]

        return RangeTotals(
            input_tokens=inp,
            output_tokens=out,
            cache_creation_tokens=cc,
            cache_read_tokens=cr,
            total_tokens=inp + out + cc + cr,
            est_api_cost_usd=_sum_cost(costs),
            session_count=count_rows[0]["sessions"] or 0 if count_rows else 0,
            project_count=proj_count,
        )

    def _daily(self, since: str, compute_cost) -> list[DailyBucket]:
        rows = self._store.query(
            f"""
            SELECT substr(datetime(ts, 'localtime'), 1, 10) as day, model, {_TOKEN_COLS}
            FROM turns
            WHERE ts >= ?
            GROUP BY day, model
            ORDER BY day
            """,
            (since,),
        )
        by_day: dict[str, DailyBucket] = {}
        costs_by_day: dict[str, list[Optional[float]]] = {}
        for r in rows:
            day = r["day"]
            if day not in by_day:
                by_day[day] = DailyBucket(date=day)
                costs_by_day[day] = []
            b = by_day[day]
            b.total_tokens += (r["inp"] or 0) + (r["out"] or 0) + (r["cc"] or 0) + (r["cr"] or 0)
            costs_by_day[day].append(_row_cost(r, r["model"], compute_cost))
        for day, b in by_day.items():
            b.est_api_cost_usd = _sum_cost(costs_by_day[day])
        return sorted(by_day.values(), key=lambda x: x.date)

    def _by_project(self, since: str, compute_cost) -> list[ProjectStats]:
        # Group by project+model to enable per-model cost computation.
        rows = self._store.query(
            f"""
            SELECT s.project_name, t.model,
              COUNT(DISTINCT t.session_id) as sessions,
              {_TOKEN_COLS}
            FROM turns t
            JOIN sessions s ON t.session_id = s.session_id
            WHERE t.ts >= ?
            GROUP BY s.project_name, t.model
            """,
            (since,),
        )
        by_proj: dict[str, ProjectStats] = {}
        costs_by_proj: dict[str, list[Optional[float]]] = {}
        for r in rows:
            name = r["project_name"]
            if name not in by_proj:
                by_proj[name] = ProjectStats(project_name=name)
                costs_by_proj[name] = []
            p = by_proj[name]
            p.total_tokens += (r["inp"] or 0) + (r["out"] or 0) + (r["cc"] or 0) + (r["cr"] or 0)
            p.session_count += r["sessions"] or 0
            costs_by_proj[name].append(_row_cost(r, r["model"], compute_cost))

        grand = sum(p.total_tokens for p in by_proj.values())
        result = []
        for name, p in by_proj.items():
            p.pct = round(100 * p.total_tokens / grand, 1) if grand else 0.0
            p.est_api_cost_usd = _sum_cost(costs_by_proj[name])
            result.append(p)
        return sorted(result, key=lambda x: -x.total_tokens)

    def _by_model(self, since: str, compute_cost) -> list[ModelStats]:
        rows = self._store.query(
            f"SELECT model, {_TOKEN_COLS} FROM turns WHERE ts >= ? GROUP BY model ORDER BY inp+out+cc+cr DESC",
            (since,),
        )
        grand = sum((r["inp"] or 0) + (r["out"] or 0) + (r["cc"] or 0) + (r["cr"] or 0) for r in rows)
        result = []
        for r in rows:
            total = (r["inp"] or 0) + (r["out"] or 0) + (r["cc"] or 0) + (r["cr"] or 0)
            result.append(ModelStats(
                model=r["model"],
                total_tokens=total,
                pct=round(100 * total / grand, 1) if grand else 0.0,
                est_api_cost_usd=_row_cost(r, r["model"], compute_cost),
            ))
        return result

    def _by_tool(self, since: str) -> list[ToolStats]:
        rows = self._store.query(
            """
            SELECT tc.tool_name, COUNT(*) as cnt
            FROM tool_calls tc
            JOIN turns t ON tc.turn_id = t.turn_id
            WHERE t.ts >= ?
            GROUP BY tc.tool_name
            ORDER BY cnt DESC
            """,
            (since,),
        )
        grand = sum(r["cnt"] or 0 for r in rows)
        return [
            ToolStats(
                tool_name=r["tool_name"],
                call_count=r["cnt"] or 0,
                pct=round(100 * (r["cnt"] or 0) / grand, 1) if grand else 0.0,
            )
            for r in rows
        ]

    def _by_hour(self, since: str) -> list[HourBucket]:
        import datetime as _dt
        offset_min = int(
            _dt.datetime.now(_dt.timezone.utc).astimezone().utcoffset().total_seconds() / 60
        )
        # Compute local hour in SQL: (utc_h*60 + utc_m + offset + 1440) keeps result positive
        rows = self._store.query(
            """
            SELECT
              CAST(((CAST(substr(ts, 12, 2) AS INTEGER) * 60
                   + CAST(substr(ts, 15, 2) AS INTEGER)
                   + ? + 1440) / 60) % 24 AS INTEGER) as hour,
              SUM(input_tokens + output_tokens + cache_creation_tokens + cache_read_tokens) as total
            FROM turns
            WHERE ts >= ?
            GROUP BY hour
            ORDER BY hour
            """,
            (offset_min, since),
        )
        by_hour = {r["hour"]: r["total"] or 0 for r in rows}
        return [HourBucket(hour=h, total_tokens=by_hour.get(h, 0)) for h in range(24)]

    def _subagents(self, since: str) -> SubagentStats:
        total = self._store.query(
            "SELECT COUNT(*) as c FROM sessions WHERE is_sidechain = 1 AND started_at >= ?",
            (since,),
        )[0]["c"] or 0
        sessions = self._store.query(
            "SELECT COUNT(*) as c FROM sessions WHERE is_sidechain = 0 AND started_at >= ?",
            (since,),
        )[0]["c"] or 1
        return SubagentStats(
            total_spawned=total,
            avg_per_session=round(total / max(sessions, 1), 1),
        )

    def _task_stats_by_project(self, since: str) -> list[ProjectTaskStats]:
        # Classify turns as execute if they called any modifying tool.
        # All other turns (read-only tools or no tools) are plan phase.
        rows = self._store.query(
            """
            WITH execute_turns AS (
              SELECT DISTINCT turn_id FROM tool_calls
              WHERE tool_name IN (
                'Edit','Write','Bash','NotebookEdit','MultiEdit','TodoWrite'
              )
            ),
            tasks AS (
              SELECT
                s.project_name,
                t.session_id,
                t.user_msg_ts,
                (JULIANDAY(MAX(t.ts)) - JULIANDAY(t.user_msg_ts)) * 86400 AS duration_secs,
                SUM(t.input_tokens + t.output_tokens + t.cache_creation_tokens + t.cache_read_tokens) AS total_tok,
                SUM(CASE WHEN et.turn_id IS NOT NULL
                    THEN t.input_tokens + t.output_tokens + t.cache_creation_tokens + t.cache_read_tokens
                    ELSE 0 END) AS execute_tok,
                SUM(CASE WHEN et.turn_id IS NULL
                    THEN t.input_tokens + t.output_tokens + t.cache_creation_tokens + t.cache_read_tokens
                    ELSE 0 END) AS plan_tok
              FROM turns t
              JOIN sessions s ON t.session_id = s.session_id
              LEFT JOIN execute_turns et ON t.turn_id = et.turn_id
              WHERE t.ts >= ? AND t.user_msg_ts != ''
              GROUP BY s.project_name, t.session_id, t.user_msg_ts
            )
            SELECT
              project_name,
              COUNT(*)            AS task_count,
              AVG(duration_secs)  AS avg_duration_secs,
              SUM(total_tok)      AS total_tokens,
              SUM(plan_tok)       AS plan_tokens,
              SUM(execute_tok)    AS execute_tokens
            FROM tasks
            GROUP BY project_name
            ORDER BY total_tokens DESC
            """,
            (since,),
        )
        return [
            ProjectTaskStats(
                project_name=r["project_name"],
                task_count=r["task_count"] or 0,
                avg_duration_secs=r["avg_duration_secs"] or 0.0,
                total_tokens=r["total_tokens"] or 0,
                plan_tokens=r["plan_tokens"] or 0,
                execute_tokens=r["execute_tokens"] or 0,
            )
            for r in rows
        ]

    def _timing_stats(self, since: str) -> TimingStats:
        rows = self._store.query(
            """
            WITH ranked AS (
              SELECT session_id, ts, user_msg_ts,
                LAG(ts) OVER (PARTITION BY session_id ORDER BY ts) as prev_ts
              FROM turns
              WHERE ts >= ?
            )
            SELECT
              (JULIANDAY(ts) - JULIANDAY(user_msg_ts)) * 86400 as proc_secs,
              CASE WHEN prev_ts IS NOT NULL AND user_msg_ts != ''
                THEN (JULIANDAY(user_msg_ts) - JULIANDAY(prev_ts)) * 86400
                ELSE NULL
              END as wait_secs
            FROM ranked
            WHERE user_msg_ts != '' AND user_msg_ts < ts
            """,
            (since,),
        )

        proc = [
            r["proc_secs"] for r in rows
            if r["proc_secs"] is not None and 0.5 < r["proc_secs"] < 600
        ]
        # Cap at 5 min — longer gaps are new independent requests, not continuations
        wait = [
            r["wait_secs"] for r in rows
            if r["wait_secs"] is not None and 1 < r["wait_secs"] < 300
        ]

        return TimingStats(
            total_processing_secs=sum(proc),
            total_wait_secs=sum(wait),
            samples=len(proc),
        )

    def _by_category(self, since: str, rules: list[dict], categorise) -> list[CategoryStats]:
        # Join with sessions to get first_user_text — turns.first_user_text is always empty.
        rows = self._store.query(
            """
            SELECT s.session_id, s.first_user_text,
              SUM(t.input_tokens + t.output_tokens + t.cache_creation_tokens + t.cache_read_tokens) as total
            FROM turns t
            JOIN sessions s ON t.session_id = s.session_id
            WHERE t.ts >= ?
            GROUP BY s.session_id
            """,
            (since,),
        )
        by_cat: dict[str, CategoryStats] = {}
        grand = 0
        for r in rows:
            total = r["total"] or 0
            grand += total
            cat = categorise(r["first_user_text"] or "", rules)
            if cat not in by_cat:
                by_cat[cat] = CategoryStats(category=cat)
            by_cat[cat].total_tokens += total
            by_cat[cat].session_count += 1

        result = sorted(by_cat.values(), key=lambda x: -x.total_tokens)
        for s in result:
            s.pct = round(100 * s.total_tokens / grand, 1) if grand else 0.0
        return result

    # ------------------------------------------------------------------
    # Export
    # ------------------------------------------------------------------

    def export(self, days: int, fmt: str = "csv") -> str:
        """Export raw turn data as CSV or JSON string."""
        from ccspy.pricing import compute_cost

        since = _since_ts(days)
        rows = self._store.query(
            """
            SELECT
              substr(t.ts, 1, 10) as date,
              s.project_name as project,
              t.model,
              t.input_tokens,
              t.output_tokens,
              t.cache_creation_tokens,
              t.cache_read_tokens,
              t.cache_creation_1h_tokens,
              t.cache_creation_5m_tokens
            FROM turns t
            JOIN sessions s ON t.session_id = s.session_id
            WHERE t.ts >= ?
            ORDER BY t.ts
            """,
            (since,),
        )

        records = []
        for r in rows:
            cost = compute_cost(
                r["model"],
                input_tokens=r["input_tokens"] or 0,
                output_tokens=r["output_tokens"] or 0,
                cache_creation_tokens=r["cache_creation_tokens"] or 0,
                cache_read_tokens=r["cache_read_tokens"] or 0,
                cache_creation_1h_tokens=r["cache_creation_1h_tokens"] or 0,
                cache_creation_5m_tokens=r["cache_creation_5m_tokens"] or 0,
            )
            records.append({
                "date": r["date"],
                "project": r["project"],
                "model": r["model"],
                "input_tokens": r["input_tokens"] or 0,
                "output_tokens": r["output_tokens"] or 0,
                "cache_creation_tokens": r["cache_creation_tokens"] or 0,
                "cache_read_tokens": r["cache_read_tokens"] or 0,
                "est_api_cost_usd": cost,
            })

        if fmt == "csv":
            import io, csv
            buf = io.StringIO()
            if records:
                writer = csv.DictWriter(buf, fieldnames=list(records[0].keys()))
                writer.writeheader()
                writer.writerows(records)
            return buf.getvalue()
        else:
            return json.dumps(records, indent=2)
