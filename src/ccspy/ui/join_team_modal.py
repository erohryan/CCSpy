"""Join team modal — enter a team name to join."""
from __future__ import annotations

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import Input, Label


class JoinTeamModal(ModalScreen[str | None]):
    """Small prompt for entering a team name to join."""

    BINDINGS = [
        Binding("escape", "dismiss_none", "Cancel", show=False),
    ]

    DEFAULT_CSS = """
    JoinTeamModal {
        align: center middle;
    }
    JoinTeamModal > Vertical {
        width: 54;
        height: 9;
        background: #1a1a2e;
        border: solid #9999cc;
        padding: 1 2;
    }
    JoinTeamModal Label {
        color: #9999cc;
        margin-bottom: 1;
    }
    JoinTeamModal #hint {
        color: #555577;
        margin-top: 1;
        margin-bottom: 0;
    }
    JoinTeamModal Input {
        background: #12122a;
        color: white;
        border: solid #444466;
    }
    """

    def compose(self) -> ComposeResult:
        with Vertical():
            yield Label("Enter team name to join")
            yield Input(
                id="team-name-input",
                placeholder="e.g. swift_wolves",
                max_length=64,
            )
            yield Label("Enter to confirm  ·  Esc to cancel", id="hint")

    def on_input_submitted(self, event: Input.Submitted) -> None:
        value = event.value.strip().lower()
        self.dismiss(value if value else None)

    def action_dismiss_none(self) -> None:
        self.dismiss(None)
