"""Opt-in modal — collect a pseudonym for the leaderboard."""
from __future__ import annotations

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import Input, Label


class OptInModal(ModalScreen[str | None]):
    """Small prompt for entering a leaderboard pseudonym."""

    BINDINGS = [
        Binding("escape", "dismiss_none", "Cancel", show=False),
    ]

    DEFAULT_CSS = """
    OptInModal {
        align: center middle;
    }
    OptInModal > Vertical {
        width: 54;
        height: 9;
        background: #1a1a2e;
        border: solid #9999cc;
        padding: 1 2;
    }
    OptInModal Label {
        color: #9999cc;
        margin-bottom: 1;
    }
    OptInModal #hint {
        color: #555577;
        margin-top: 1;
        margin-bottom: 0;
    }
    OptInModal Input {
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
            yield Label("Choose a leaderboard pseudonym")
            yield Input(
                value=self._current,
                id="pseudonym-input",
                placeholder="e.g. turbodev",
                max_length=24,
            )
            yield Label("Enter to confirm  ·  Esc to cancel", id="hint")

    def on_input_submitted(self, event: Input.Submitted) -> None:
        value = event.value.strip()
        self.dismiss(value if value else None)

    def action_dismiss_none(self) -> None:
        self.dismiss(None)
