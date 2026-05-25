"""Uncategorised session analysis — suggestions + existing category management."""
from __future__ import annotations

from pathlib import Path

from textual.app import ComposeResult
from textual.binding import Binding
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
    SuggestScreen #suggest-body { height: 1fr; padding: 0 0; color: #7a7a9a; overflow-y: auto; }
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
        yield Static("", id="suggest-body")
        yield _Footer()

    def on_mount(self) -> None:
        self._render()

    def _render(self) -> None:
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

    # ------------------------------------------------------------------
    # Keyboard
    # ------------------------------------------------------------------

    def on_key(self, event) -> None:
        key = event.key
        if key in ("j", "down"):
            if self._total > 0:
                self._cursor = (self._cursor + 1) % self._total
                self._render()
            event.stop()
        elif key in ("k", "up"):
            if self._total > 0:
                self._cursor = (self._cursor - 1) % self._total
                self._render()
            event.stop()
        elif key == "space":
            if self._cursor < self._n_suggest:
                self._rules[self._cursor].accepted = not self._rules[self._cursor].accepted
                self._render()
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
            self._render()

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------

    def action_accept_checked(self) -> None:
        from ccspy.suggest import append_rules
        n = append_rules(self._rules, self._categories_path)
        self.app.pop_screen()
        self._on_accept(n)

    def action_edit_file(self) -> None:
        import subprocess, os
        editor = os.environ.get("EDITOR", "nano")
        with self.app.suspend():
            subprocess.run([editor, str(self._categories_path)])
        self.app.pop_screen()
        self._on_accept(0)
