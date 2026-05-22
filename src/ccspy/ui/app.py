"""Textual App root."""
from __future__ import annotations

from pathlib import Path

from textual.app import App, ComposeResult
from textual.binding import Binding

from ccspy.store import Store
from ccspy.ui.dashboard import DashboardScreen

_CSS = Path(__file__).parent / "theme.css"


class CcspyApp(App):
    """ccspy — Claude Code Spy."""

    CSS_PATH = str(_CSS)
    BINDINGS = [
        Binding("ctrl+c", "quit", "Quit", show=False),
    ]

    def __init__(self, store: Store, range_days: int = 7) -> None:
        super().__init__()
        self._store = store
        self._range_days = range_days

    def on_mount(self) -> None:
        self.push_screen(DashboardScreen(store=self._store, range_days=self._range_days))
