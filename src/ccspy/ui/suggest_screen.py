"""Uncategorised session analysis screen — keyword suggestions + accept/edit flow."""
from __future__ import annotations

from textual.app import ComposeResult
from textual.binding import Binding
from textual.screen import Screen
from textual.widgets import Static
from textual.containers import ScrollableContainer
from textual.widget import Widget
from rich.text import Text

from ccspy.suggest import SuggestedRule
from ccspy.ui.widgets._format import fmt_tokens


# ---------------------------------------------------------------------------
# Sub-widgets
# ---------------------------------------------------------------------------

class _Header(Static):
    DEFAULT_CSS = "_Header { height: 2; background: #12122a; color: #7a7a9a; padding: 0 2; }"


class _Footer(Static):
    DEFAULT_CSS = "_Footer { height: 1; background: #12122a; color: #555577; padding: 0 2; }"

    def render(self) -> str:
        return "Space toggle   a accept checked   e edit in $EDITOR   Esc back"


class SuggestionRow(Widget):
    """One toggleable suggested rule row."""

    DEFAULT_CSS = """
    SuggestionRow {
        height: 4;
        padding: 0 2;
        color: #7a7a9a;
    }
    SuggestionRow:focus {
        background: #1a1a3a;
    }
    """

    def __init__(self, rule: SuggestedRule, index: int, **kwargs) -> None:
        super().__init__(**kwargs)
        self._rule = rule
        self._index = index
        self.can_focus = True

    def toggle(self) -> None:
        self._rule.accepted = not self._rule.accepted
        self.refresh()

    def render(self) -> Text:
        r = self._rule
        t = Text()

        check = "✓" if r.accepted else "·"
        check_style = "bold #44cf6c" if r.accepted else "dim"
        t.append(f"  {check}  ", style=check_style)

        keywords = "  ".join(r.match_any[:5])
        t.append(f"{keywords:<40}", style="white" if r.accepted else "dim")

        t.append("→  ", style="dim")
        t.append(f"{r.suggested_name}", style="bold #9999cc" if r.accepted else "dim")
        t.append(f"  ({r.session_count} sessions)\n", style="dim")

        # Sample message
        sample = r.sample_texts[0] if r.sample_texts else ""
        if sample:
            t.append(f'       “{sample[:90]}”\n', style="dim #555577" if r.accepted else "dim #3a3a5a")

        return t

    def on_key(self, event) -> None:
        if event.key == "space":
            self.toggle()
            event.stop()


# ---------------------------------------------------------------------------
# Main screen
# ---------------------------------------------------------------------------

class SuggestScreen(Screen):
    """Keyword-cluster suggestions for uncategorised sessions."""

    BINDINGS = [
        Binding("escape", "app.pop_screen", "Back", show=False),
        Binding("a", "accept_all", "accept", show=False),
        Binding("e", "edit_file", "edit", show=False),
        Binding("space", "toggle_focused", "toggle", show=False),
        Binding("j,down", "focus_next", "next", show=False),
        Binding("k,up", "focus_previous", "prev", show=False),
    ]

    DEFAULT_CSS = """
    SuggestScreen { background: #0d0d1a; }
    SuggestScreen ScrollableContainer { height: 1fr; }
    """

    def __init__(
        self,
        rules: list[SuggestedRule],
        uncategorised_count: int,
        uncategorised_tokens: int,
        categories_path,
        on_accept,
    ) -> None:
        super().__init__()
        self._rules = rules
        self._count = uncategorised_count
        self._tokens = uncategorised_tokens
        self._categories_path = categories_path
        self._on_accept = on_accept

    def compose(self) -> ComposeResult:
        tok = fmt_tokens(self._tokens)
        if self._rules:
            subtitle = f"u  Uncategorised: {self._count} sessions · {tok} tokens · {len(self._rules)} suggestions"
        else:
            subtitle = f"u  Uncategorised: {self._count} sessions · {tok} tokens · no patterns found (try a wider range)"
        yield _Header(subtitle)
        yield ScrollableContainer(
            *[
                SuggestionRow(rule, i, id=f"rule-{i}")
                for i, rule in enumerate(self._rules)
            ]
        )
        yield _Footer()

    def on_mount(self) -> None:
        if self._rules:
            self.query_one("#rule-0").focus()

    def action_toggle_focused(self) -> None:
        focused = self.focused
        if isinstance(focused, SuggestionRow):
            focused.toggle()

    def action_accept_all(self) -> None:
        from ccspy.suggest import append_rules
        n = append_rules(self._rules, self._categories_path)
        self.app.pop_screen()
        self._on_accept(n)

    def action_edit_file(self) -> None:
        import subprocess, sys
        editor = __import__("os").environ.get("EDITOR", "nano")
        with self.app.suspend():
            subprocess.run([editor, str(self._categories_path)])
        self.app.pop_screen()
        self._on_accept(0)
