"""Command palette — fuzzy-search over all dashboard actions."""
from __future__ import annotations

from textual.app import ComposeResult
from textual.binding import Binding
from textual.screen import ModalScreen
from textual.containers import Vertical
from textual.widgets import Input, Label, ListView, ListItem

PALETTE_ACTIONS: list[dict] = [
    {"key": "range",           "param": "1",  "label": "Range: 1 day",       "desc": "last 24 hours"},
    {"key": "range",           "param": "7",  "label": "Range: 7 days",       "desc": "last 7 days (default)"},
    {"key": "range",           "param": "30", "label": "Range: 30 days",      "desc": "last 30 days"},
    {"key": "projects",        "param": None, "label": "Browse projects",      "desc": "drill into per-project token usage"},
    {"key": "sessions",        "param": None, "label": "Browse sessions",      "desc": "explore recent sessions (last 50)"},
    {"key": "tools",           "param": None, "label": "Browse tools",         "desc": "tool call breakdown and drill-down"},
    {"key": "edit_categories", "param": None, "label": "Edit categories",      "desc": "open categories.toml in $EDITOR"},
    {"key": "export_csv",      "param": None, "label": "Export CSV",           "desc": "save current view to ~/ccspy-export.csv"},
    {"key": "reload",          "param": None, "label": "Reload data",          "desc": "force resync from ~/.claude/"},
    {"key": "pricing",         "param": None, "label": "Pricing table",        "desc": "show model pricing rates (api-equiv)"},
    {"key": "sources",         "param": None, "label": "Data sources",         "desc": "JSONL file stats and cache info"},
    {"key": "help",            "param": None, "label": "Help / shortcuts",     "desc": "keyboard shortcut reference"},
]


class CommandPaletteScreen(ModalScreen[tuple | None]):
    """Fuzzy-search command palette — Esc or Enter to act."""

    BINDINGS = [
        Binding("escape", "dismiss_none", "Close", show=False),
        Binding("up", "cursor_up", "Up", show=False, priority=True),
        Binding("down", "cursor_down", "Down", show=False, priority=True),
    ]

    DEFAULT_CSS = """
    CommandPaletteScreen { align: center middle; }
    CommandPaletteScreen > Vertical {
        width: 70;
        height: auto;
        max-height: 26;
        background: #1a1a2e;
        border: solid #2ac3de;
        padding: 1 2;
    }
    CommandPaletteScreen Label { color: #7a7a9a; margin-bottom: 1; }
    CommandPaletteScreen Input {
        background: #12122a;
        color: white;
        border: solid #444466;
        margin-bottom: 1;
    }
    CommandPaletteScreen ListView {
        background: #1a1a2e;
        border: none;
        height: auto;
        max-height: 16;
    }
    CommandPaletteScreen ListItem { padding: 0 1; }
    """

    def __init__(self, store, data, focus: str = "") -> None:
        super().__init__()
        self._store = store
        self._data = data
        self._focus = focus
        self._filtered: list[dict] = list(PALETTE_ACTIONS)

    def compose(self) -> ComposeResult:
        with Vertical():
            yield Label(": command palette   ↑↓ navigate   Enter select   Esc cancel")
            yield Input(id="palette-input", placeholder="type to filter actions…")
            yield ListView(*self._build_items(self._filtered), id="palette-list")

    def on_mount(self) -> None:
        inp = self.query_one("#palette-input", Input)
        inp.focus()
        if self._focus:
            inp.value = self._focus
            self._apply_filter(self._focus)

    def _build_items(self, actions: list[dict]) -> list[ListItem]:
        from rich.text import Text
        items = []
        for a in actions:
            t = Text()
            t.append(f"{a['label']:<26}", style="white")
            t.append(a["desc"], style="#555577")
            items.append(ListItem(Label(t)))
        return items

    def on_input_changed(self, event: Input.Changed) -> None:
        self._apply_filter(event.value)

    def _apply_filter(self, query: str) -> None:
        q = query.lower().strip()
        self._filtered = [
            a for a in PALETTE_ACTIONS
            if not q or q in a["label"].lower() or q in a["desc"].lower()
        ]
        lv = self.query_one("#palette-list", ListView)
        lv.clear()
        for item in self._build_items(self._filtered):
            lv.append(item)

    def on_input_submitted(self, _event: Input.Submitted) -> None:
        lv = self.query_one("#palette-list", ListView)
        idx = lv.index
        candidates = self._filtered
        if idx is not None and 0 <= idx < len(candidates):
            a = candidates[idx]
        elif candidates:
            a = candidates[0]
        else:
            self.dismiss(None)
            return
        self.dismiss((a["key"], a.get("param")))

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        idx = event.list_view.index
        if idx is not None and 0 <= idx < len(self._filtered):
            a = self._filtered[idx]
            self.dismiss((a["key"], a.get("param")))

    def action_dismiss_none(self) -> None:
        self.dismiss(None)

    def action_cursor_up(self) -> None:
        self.query_one("#palette-list", ListView).action_cursor_up()

    def action_cursor_down(self) -> None:
        self.query_one("#palette-list", ListView).action_cursor_down()
