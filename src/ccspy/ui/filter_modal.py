"""Filter modal — type a project name substring to filter all panels."""
from __future__ import annotations

from textual.app import ComposeResult
from textual.binding import Binding
from textual.screen import ModalScreen
from textual.widgets import Input, Label
from textual.containers import Vertical


class FilterModal(ModalScreen[str | None]):
    """Small inline modal for entering a project filter string."""

    BINDINGS = [
        Binding("escape", "dismiss_none", "Cancel", show=False),
    ]

    DEFAULT_CSS = """
    FilterModal {
        align: center middle;
    }
    FilterModal > Vertical {
        width: 50;
        height: 7;
        background: #1a1a2e;
        border: solid #2ac3de;
        padding: 1 2;
    }
    FilterModal Label {
        color: #7a7a9a;
        margin-bottom: 1;
    }
    FilterModal Input {
        background: #12122a;
        color: white;
        border: solid #444466;
    }
    """

    def __init__(self, current: str = "", **kwargs) -> None:
        super().__init__(**kwargs)
        self._current = current

    def compose(self) -> ComposeResult:
        with Vertical():
            yield Label("Filter by project name (empty = show all, Esc = cancel)")
            yield Input(value=self._current, id="filter-input", placeholder="project substring…")

    def on_input_submitted(self, event: Input.Submitted) -> None:
        self.dismiss(event.value.strip())

    def action_dismiss_none(self) -> None:
        self.dismiss(None)
