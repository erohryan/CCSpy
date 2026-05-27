"""Uncategorised session analysis — suggestions + existing category management."""
from __future__ import annotations

from pathlib import Path

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import ScrollableContainer
from textual.screen import Screen
from textual.widgets import Static
from rich.text import Text

from ccspy.suggest import SuggestedRule
from ccspy.ui.widgets._format import fmt_tokens


class _Header(Static):
    DEFAULT_CSS = "_Header { height: 1; background: #12122a; color: #7a7a9a; padding: 0 2; }"


class _Footer(Static):
    DEFAULT_CSS = "_Footer { height: 1; background: #12122a; color: #555577; padding: 0 2; }"

    def render(self) -> str:
        return "j/↓ k/↑ navigate   Space toggle new   d delete rule   a accept new   e edit file   Esc back"


class SuggestScreen(Screen):
    """Keyword-cluster suggestions + existing category viewer/editor."""

    BINDINGS = [
        Binding("escape", "app.pop_screen", "Back", show=False),
        Binding("a", "accept_checked", "accept", show=False),
        Binding("e", "edit_file", "edit", show=False),
    ]

    DEFAULT_CSS = """
    SuggestScreen { background: #0d0d1a; }
    SuggestScreen ScrollableContainer { height: 1fr; }
    SuggestScreen #suggest-body { color: #7a7a9a; }
    """

    def __init__(
        self,
        rules: list[SuggestedRule],
        uncategorised_count: int,
        uncategorised_tokens: int,
        categories_path: Path,
        existing_rules: list[dict],
        on_accept,
    ) -> None:
        super().__init__()
        self._rules = rules
        self._count = uncategorised_count
        self._tokens = uncategorised_tokens
        self._categories_path = categories_path
        self._existing = list(existing_rules)
        self._on_accept = on_accept
        self._cursor = 0

    @property
    def _n_suggest(self) -> int:
        return len(self._rules)

    @property
    def _n_existing(self) -> int:
        return len(self._existing)

    @property
    def _total(self) -> int:
        return self._n_suggest + self._n_existing

    def compose(self) -> ComposeResult:
        tok = fmt_tokens(self._tokens)
        n_rules = self._n_existing
        parts = [f"u  Uncategorised: {self._count} sessions · {tok} tokens"]
        parts.append(f"{self._n_suggest} suggestions" if self._rules else "no patterns found")
        parts.append(f"{n_rules} existing rules")
        yield _Header("  ·  ".join(parts))
        yield ScrollableContainer(Static("", id="suggest-body"), id="suggest-scroll")
        yield _Footer()

    def on_mount(self) -> None:
        # Prevent ScrollableContainer from stealing arrow keys
        self.query_one("#suggest-scroll", ScrollableContainer).can_focus = False
        self._draw()

    def _draw(self) -> None:
        t = Text()

        # ── New suggestions ───────────────────────────────────────────────
        t.append("\n  NEW SUGGESTIONS\n", style="bold #7a7a9a")
        t.append("  " + "─" * 66 + "\n", style="dim #2d2d4e")

        if self._rules:
            for i, r in enumerate(self._rules):
                sel = self._cursor == i
                bg = " on #1a1a3a" if sel else ""
                check = "✓" if r.accepted else "·"
                check_style = f"bold #44cf6c{bg}" if r.accepted else f"dim{bg}"

                t.append(f"  {check}  ", style=check_style)
                keywords = "  ".join(r.match_any[:5])
                t.append(f"{keywords:<36}", style=f"white{bg}" if r.accepted else f"dim{bg}")
                t.append("→  ", style=f"dim{bg}")
                t.append(r.suggested_name, style=f"bold #9999cc{bg}" if r.accepted else f"dim{bg}")
                t.append(f"  ({r.session_count} sessions)\n", style=f"dim{bg}")

                sample = r.sample_texts[0] if r.sample_texts else ""
                if sample:
                    t.append(f'       "{sample[:86]}"\n', style=f"dim #555577{bg}" if r.accepted else f"dim #3a3a5a{bg}")
        else:
            t.append("  No patterns found — accumulate more uncategorised sessions.\n", style="dim")

        # ── Existing rules ────────────────────────────────────────────────
        t.append("\n  EXISTING RULES\n", style="bold #7a7a9a")
        t.append("  " + "─" * 66 + "\n", style="dim #2d2d4e")

        for j, rule in enumerate(self._existing):
            i = self._n_suggest + j
            sel = self._cursor == i
            bg = " on #1a1a3a" if sel else ""
            category = rule.get("category", "?")
            keywords = rule.get("match_any", [])
            kw_str = ", ".join(str(k) for k in keywords[:7])
            if len(keywords) > 7:
                kw_str += f" +{len(keywords) - 7}"

            marker = "▶ " if sel else "  "
            t.append(f"  {marker}", style=f"bold #cc6644{bg}" if sel else f"dim{bg}")
            t.append(f"{category:<18}", style=f"bold white{bg}" if sel else f"#9999cc{bg}")
            t.append(f"  {kw_str}\n", style=f"dim #777799{bg}")

        t.append("\n")
        self.query_one("#suggest-body", Static).update(t)
        self._scroll_to_cursor()

    def _cursor_y(self) -> int:
        """Approximate line number of the cursor for scroll-into-view."""
        y = 2  # blank line + section header + divider = 3 lines
        if self._cursor < self._n_suggest:
            for i in range(self._cursor):
                y += 2 if self._rules[i].sample_texts else 1
            return y
        # Past suggestions
        for r in self._rules:
            y += 2 if r.sample_texts else 1
        y += 3  # blank + existing header + divider
        y += self._cursor - self._n_suggest
        return y

    def _scroll_to_cursor(self) -> None:
        try:
            sc = self.query_one("#suggest-scroll", ScrollableContainer)
            sc.scroll_to(y=max(0, self._cursor_y() - 3), animate=False)
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Keyboard
    # ------------------------------------------------------------------

    def on_key(self, event) -> None:
        key = event.key
        if key in ("j", "down"):
            if self._total > 0:
                self._cursor = (self._cursor + 1) % self._total
                self._draw()
            event.stop()
        elif key in ("k", "up"):
            if self._total > 0:
                self._cursor = (self._cursor - 1) % self._total
                self._draw()
            event.stop()
        elif key == "space":
            if self._cursor < self._n_suggest:
                self._rules[self._cursor].accepted = not self._rules[self._cursor].accepted
                self._draw()
            event.stop()
        elif key == "d":
            if self._cursor >= self._n_suggest:
                self._delete_selected()
            event.stop()

    def _delete_selected(self) -> None:
        from ccspy.suggest import delete_rule
        j = self._cursor - self._n_suggest
        rule = self._existing[j]
        category = rule.get("category", "")
        if not category:
            return
        if delete_rule(category, self._categories_path):
            self._existing.pop(j)
            self._cursor = min(self._cursor, max(0, self._total - 1))
            self.notify(f'Deleted "{category}"', title="ccspy")
            self._draw()

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------

    def action_accept_checked(self) -> None:
        from ccspy.suggest import append_rules
        n = append_rules(self._rules, self._categories_path)
        self.app.pop_screen()
        self._on_accept(n)

    def action_edit_file(self) -> None:
        import subprocess
        from ccspy._paths import default_editor
        with self.app.suspend():
            subprocess.run([default_editor(), str(self._categories_path)])
        self.app.pop_screen()
        self._on_accept(0)
