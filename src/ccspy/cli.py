"""Typer CLI — subcommands and entry-point for ccspy."""
from __future__ import annotations

from enum import Enum
from pathlib import Path
from typing import Optional

import typer

app = typer.Typer(
    name="ccspy",
    help="Claude Code session token-usage analytics. ccspy is read-only — it never modifies your Claude Code data.",
    no_args_is_help=False,
    add_completion=False,
)


class Range(str, Enum):
    today = "1d"
    week = "7d"
    month = "30d"


class ExportFormat(str, Enum):
    csv = "csv"
    json = "json"


def _launch_dashboard(range_days: int) -> None:
    """Import and run the Textual app."""
    from ccspy.store import Store
    from ccspy.ui.app import CcspyApp

    store = Store.open()
    store.sync()
    app = CcspyApp(store=store, range_days=range_days)
    app.run()


@app.callback(invoke_without_command=True)
def default(
    ctx: typer.Context,
    version: bool = typer.Option(False, "--version", "-V", help="Show version and exit.", is_eager=True),
) -> None:
    """Open the dashboard (default range = 7d)."""
    if version:
        from ccspy import __version__
        typer.echo(f"ccspy {__version__}")
        raise typer.Exit()
    if ctx.invoked_subcommand is None:
        _launch_dashboard(range_days=7)


@app.command()
def today() -> None:
    """Open dashboard since midnight local time today."""
    _launch_dashboard(range_days=0)


@app.command()
def week() -> None:
    """Open dashboard with range = 7d."""
    _launch_dashboard(range_days=7)


@app.command()
def month() -> None:
    """Open dashboard with range = 30d."""
    _launch_dashboard(range_days=30)


@app.command()
def export(
    range: str = typer.Option("7d", "--range", "-r", help="Time range: 1d, 7d, 30d, or NNd."),
    format: ExportFormat = typer.Option(ExportFormat.csv, "--format", "-f", help="Output format."),
    out: Optional[Path] = typer.Option(None, "--out", "-o", help="Output path (default: stdout)."),
) -> None:
    """Export session data to CSV or JSON."""
    from ccspy.store import Store
    from ccspy.aggregator import Aggregator

    store = Store.open()
    store.sync()

    try:
        days = int(range.rstrip("d"))
    except ValueError:
        typer.echo(f"Invalid range '{range}'. Use format like '7d'.", err=True)
        raise typer.Exit(1)

    agg = Aggregator(store)
    data = agg.export(days=days, fmt=format.value)

    if out:
        out.write_text(data, encoding="utf-8")
        typer.echo(f"Exported to {out}")
    else:
        typer.echo(data)


cache_app = typer.Typer(help="Manage the ccspy SQLite cache.")
app.add_typer(cache_app, name="cache")


@cache_app.command("clear")
def cache_clear() -> None:
    """Delete the SQLite cache database."""
    from ccspy.store import Store

    path = Store.db_path()
    if path.exists():
        path.unlink()
        typer.echo(f"Cache cleared: {path}")
    else:
        typer.echo("No cache found.")


@cache_app.command("rebuild")
def cache_rebuild() -> None:
    """Delete and rebuild the SQLite cache from scratch."""
    from ccspy.store import Store

    path = Store.db_path()
    if path.exists():
        path.unlink()
    store = Store.open()
    store.sync(force=True)
    typer.echo("Cache rebuilt.")
