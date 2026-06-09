"""Plan picker modal — choose subscription tier for break-even tracking."""
from __future__ import annotations

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import Input, Label, ListView, ListItem
from rich.text import Text

from ccspy.plan import PLANS


class _CustomAmountModal(ModalScreen[float | None]):
    """Secondary modal: enter a custom monthly cost."""

    BINDINGS = [Binding("escape", "dismiss_none", "Cancel", show=False)]

    DEFAULT_CSS = """
    _CustomAmountModal { align: center middle; }
    _CustomAmountModal > Vertical {
        width: 50; height: 8;
        background: #1a1a2e; border: solid #9999cc; padding: 1 2;
    }
    _CustomAmountModal Label { color: #9999cc; margin-bottom: 1; }
    _CustomAmountModal #hint { color: #555577; margin-top: 1; }
    _CustomAmountModal Input { background: #12122a; color: white; border: solid #444466; }
    """

    def compose(self) -> ComposeResult:
        with Vertical():
            yield Label("Monthly plan cost (USD)")
            yield Input(placeholder="e.g. 50", id="cost-input")
            yield Label("Enter to confirm  ·  Esc to cancel", id="hint")

    def on_input_submitted(self, event: Input.Submitted) -> None:
        try:
            val = float(event.value.strip().lstrip("$"))
            self.dismiss(val if val >= 0 else None)
        except ValueError:
            self.dismiss(None)

    def action_dismiss_none(self) -> None:
        self.dismiss(None)


class PlanModal(ModalScreen[tuple[str, float] | None]):
    """Pick a subscription plan; returns (name, monthly_cost) or None."""

    BINDINGS = [
        Binding("escape",     "dismiss_none", "Cancel", show=False),
        Binding("up",         "cursor_up",    "Up",     show=False, priority=True),
        Binding("down",       "cursor_down",  "Down",   show=False, priority=True),
        Binding("enter",      "select",       "Select", show=False),
    ]

    DEFAULT_CSS = """
    PlanModal { align: center middle; }
    PlanModal > Vertical {
        width: 52; height: auto; max-height: 20;
        background: #1a1a2e; border: solid #9999cc; padding: 1 2;
    }
    PlanModal #title  { color: #9999cc; margin-bottom: 0; }
    PlanModal #hint   { color: #555577; margin-top: 1; }
    PlanModal ListView { background: #1a1a2e; border: none; height: auto; max-height: 12; }
    PlanModal ListItem { padding: 0 1; color: #7a7a9a; }
    PlanModal ListItem.--highlight { background: #2d2d4e; color: white; }
    """

    def __init__(self, current_name: str = "", **kwargs) -> None:
        super().__init__(**kwargs)
        self._current = current_name

    def compose(self) -> ComposeResult:
        from ccspy.plan import get_monthly_cost
        current_cost = get_monthly_cost()

        with Vertical():
            yield Label("Subscription plan  ·  break-even tracking", id="title")
            lv = ListView(id="plan-list")
            yield lv
            yield Label("↑↓ navigate  ·  Enter select  ·  Esc cancel", id="hint")

    def on_mount(self) -> None:
        lv = self.query_one("#plan-list", ListView)
        rows = [*PLANS, ("custom", "Custom", -1.0)]
        for key, name, cost in rows:
            label = f"  {name:<10}  " + (f"${cost:.0f}/mo" if cost >= 0 else "enter amount")
            if key == self._current:
                label += "  ◀ current"
            item = ListItem(Label(label), id=f"plan-{key}")
            lv.append(item)
        lv.focus()

    def action_cursor_up(self) -> None:
        self.query_one("#plan-list", ListView).action_scroll_up()

    def action_cursor_down(self) -> None:
        self.query_one("#plan-list", ListView).action_scroll_down()

    def action_select(self) -> None:
        lv = self.query_one("#plan-list", ListView)
        if lv.highlighted_child is None:
            return
        item_id = lv.highlighted_child.id or ""
        key = item_id.removeprefix("plan-")
        if key == "custom":
            self.app.push_screen(_CustomAmountModal(), self._handle_custom)
            return
        for k, name, cost in PLANS:
            if k == key:
                self.dismiss((name, cost))
                return

    def _handle_custom(self, cost: float | None) -> None:
        if cost is not None:
            self.dismiss(("Custom", cost))
        # else stay open (user cancelled inner modal)

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        self.action_select()

    def action_dismiss_none(self) -> None:
        self.dismiss(None)
