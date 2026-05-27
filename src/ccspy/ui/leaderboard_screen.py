"""Community leaderboard screen — opt-in, peak daily tokens."""
from __future__ import annotations

import threading
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import ScrollableContainer
from textual.screen import Screen
from textual.widgets import Static
from rich.text import Text


# ── Podium dimensions ─────────────────────────────────────────────────────────
_SW   = 14   # side panel inner width
_CW   = 22   # centre panel inner width
_IND  = "  " # left indent
_GAP  = "   " # gap between panels

_GOLD   = "#FFD700"
_SILVER = "#C0C0C0"
_BRONZE = "#CD7F32"


def _fmt(n: int) -> str:
    if n >= 1_000_000:
        return f"{n / 1_000_000:.2f}M"
    if n >= 1_000:
        return f"{n / 1_000:.1f}K"
    return f"{n:,}"


def _trunc(s: str, w: int) -> str:
    return s[:w]


class _Header(Static):
    DEFAULT_CSS = "_Header { height: 1; background: #12122a; color: #7a7a9a; padding: 0 2; }"


class _Footer(Static):
    DEFAULT_CSS = "_Footer { height: 1; background: #12122a; color: #555577; padding: 0 2; }"

    def render(self) -> str:
        return "r refresh   i join / update score   o opt out   Esc back"


class LeaderboardScreen(Screen):
    """Opt-in community leaderboard — peak tokens in a single day."""

    BINDINGS = [
        Binding("escape", "app.pop_screen", "Back",    show=False),
        Binding("r",      "refresh",        "refresh", show=False),
        Binding("i",      "optin_flow",     "opt in",  show=False),
        Binding("o",      "optout",         "opt out", show=False),
    ]

    DEFAULT_CSS = """
    LeaderboardScreen { background: #0d0d1a; }
    LeaderboardScreen ScrollableContainer { height: 1fr; }
    """

    def __init__(self, store) -> None:
        super().__init__()
        self._store  = store
        self._top:   list[dict] = []
        self._rank:  int | None = None
        self._peak:  int        = 0
        self._loading            = True
        self._error: str         = ""

    def compose(self) -> ComposeResult:
        yield _Header("ccspy  ·  leaderboard  ·  peak tokens in a single day")
        yield ScrollableContainer(Static("", id="lb-body"), id="lb-scroll")
        yield _Footer()

    def on_mount(self) -> None:
        self.query_one("#lb-scroll", ScrollableContainer).can_focus = False
        self._draw()
        self.action_refresh()

    # ------------------------------------------------------------------
    # Data loading
    # ------------------------------------------------------------------

    def action_refresh(self) -> None:
        from ccspy import leaderboard as lb

        cache = lb.load_cache()
        if cache:
            self._top   = cache.get("top", [])
            self._rank  = cache.get("rank")
            self._peak  = cache.get("peak", 0)
            self._loading = False
            self._draw()
        else:
            self._loading = True
            self._draw()

        threading.Thread(target=self._fetch_data, daemon=True).start()

    def _fetch_data(self) -> None:
        from ccspy import leaderboard as lb

        try:
            top  = lb.fetch_top(10)
            peak = lb.peak_day_tokens(self._store)
            rank = None
            if lb.is_opted_in():
                lb.push_score(self._store)
                rank = lb.fetch_rank(lb.get_user_token(), peak)
            lb.save_cache(top, rank, peak)
            self._top   = top
            self._rank  = rank
            self._peak  = peak
            self._error = ""
        except Exception as exc:
            self._error = str(exc)[:80]
        finally:
            self._loading = False
            self.call_from_thread(self._draw)

    # ------------------------------------------------------------------
    # Rendering
    # ------------------------------------------------------------------

    def _draw(self) -> None:
        from ccspy import leaderboard as lb

        opted_in  = lb.is_opted_in()
        pseudonym = lb.get_pseudonym()

        t = Text()
        t.append("\n")
        t.append("  CCSPY LEADERBOARD\n", style="bold white")
        t.append("  Peak tokens consumed in a single day\n\n", style="dim #7a7a9a")

        if not lb.configured():
            t.append("  Leaderboard backend not yet configured.\n\n", style="dim #cc6644")
            t.append("  To enable:\n", style="dim #7a7a9a")
            t.append("  1. Create a free project at supabase.com\n", style="dim #555577")
            t.append("  2. Run the SQL setup from the top of leaderboard.py\n", style="dim #555577")
            t.append("  3. Set SUPABASE_URL and SUPABASE_ANON_KEY in leaderboard.py\n", style="dim #555577")
        elif self._loading and not self._top:
            t.append("  Connecting…\n", style="dim #7a7a9a")
        elif not self._top:
            t.append("  No entries yet — be the first!\n", style="dim")
            if not opted_in:
                t.append("  Press i to join the leaderboard.\n", style="dim #9999cc")
        else:
            self._draw_podium(t)
            self._draw_rest(t)

        # Personal rank bar
        t.append("\n  " + "─" * 56 + "\n", style="dim #2d2d4e")
        if opted_in:
            rank_s  = f"#{self._rank}" if self._rank else "unranked"
            peak_s  = _fmt(self._peak) if self._peak else "─"
            t.append(f'  You: {rank_s}  "{pseudonym}"  ·  {peak_s} tok/day\n', style="bold #9999cc")
        else:
            t.append("  You are not on the leaderboard. ", style="dim #7a7a9a")
            t.append("Press i to join.\n", style="#9999cc")
        t.append("  " + "─" * 56 + "\n", style="dim #2d2d4e")

        if self._error:
            t.append(f"\n  Network error: {self._error}\n", style="dim #cc4444")

        self.query_one("#lb-body", Static).update(t)

    def _draw_podium(self, t: Text) -> None:
        top = self._top
        e   = [top[i] if i < len(top) else None for i in range(3)]
        e1, e2, e3 = e[0], e[1], e[2]

        def name(entry: dict | None, w: int) -> str:
            if not entry:
                return "─" * min(4, w)
            return _trunc(entry.get("pseudonym", "?"), w)

        def score(entry: dict | None) -> str:
            if not entry:
                return "─"
            return f"{entry.get('peak_day', 0):,}"

        def _box_top(w: int, color: str) -> None:
            t.append(f"┌{'─'*w}┐", style=f"bold {color}")

        def _box_bot(w: int, color: str) -> None:
            t.append(f"└{'─'*w}┘", style=f"dim {color}")

        def _cell(content: str, w: int, color: str, bold: bool = False) -> None:
            inner = f" {_trunc(content, w-2):<{w-2}} "
            style = f"bold {color}" if bold else color
            t.append(f"│{inner}│", style=style)

        # ── Top borders ───────────────────────────────────────────────
        t.append(_IND)
        _box_top(_SW, _SILVER)
        t.append(_GAP)
        _box_top(_CW, _GOLD)
        t.append(_GAP)
        _box_top(_SW, _BRONZE)
        t.append("\n")

        # ── Rank / medal row ──────────────────────────────────────────
        t.append(_IND)
        _cell(f"✦  #2", _SW, _SILVER, bold=True)
        t.append(_GAP)
        _cell(f"★   #1", _CW, _GOLD,   bold=True)
        t.append(_GAP)
        _cell(f"·  #3", _SW, _BRONZE, bold=True)
        t.append("\n")

        # ── Name row ──────────────────────────────────────────────────
        t.append(_IND)
        _cell(name(e2, _SW - 2), _SW, _SILVER, bold=True)
        t.append(_GAP)
        _cell(name(e1, _CW - 2), _CW, _GOLD,   bold=True)
        t.append(_GAP)
        _cell(name(e3, _SW - 2), _SW, _BRONZE, bold=True)
        t.append("\n")

        # ── Score row ─────────────────────────────────────────────────
        t.append(_IND)
        _cell(score(e2), _SW, _SILVER)
        t.append(_GAP)
        _cell(score(e1), _CW, _GOLD)
        t.append(_GAP)
        _cell(score(e3), _SW, _BRONZE)
        t.append("\n")

        # ── Bottom borders ────────────────────────────────────────────
        t.append(_IND)
        _box_bot(_SW, _SILVER)
        t.append(_GAP)
        _box_bot(_CW, _GOLD)
        t.append(_GAP)
        _box_bot(_SW, _BRONZE)
        t.append("\n\n")

    def _draw_rest(self, t: Text) -> None:
        for i, entry in enumerate(self._top[3:], start=4):
            name  = _trunc(entry.get("pseudonym", "?"), 20)
            score = f"{entry.get('peak_day', 0):,}"
            t.append(f"  #{i:<3} {name:<22} {score:>14} tok\n", style="dim #7a7a9a")

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------

    def action_optin_flow(self) -> None:
        from ccspy import leaderboard as lb
        from ccspy.ui.optin_modal import OptInModal
        current = lb.get_pseudonym() if lb.is_opted_in() else ""
        self.app.push_screen(OptInModal(current=current), self._handle_optin)

    def _handle_optin(self, pseudonym: str | None) -> None:
        if not pseudonym:
            return
        from ccspy import leaderboard as lb
        lb.opt_in(pseudonym)
        self.notify(f'Joined as "{pseudonym}"', title="ccspy leaderboard")
        self.action_refresh()

    def action_optout(self) -> None:
        from ccspy import leaderboard as lb
        if lb.is_opted_in():
            name = lb.get_pseudonym()
            lb.opt_out()
            self.notify(f'Removed "{name}" from leaderboard', title="ccspy")
            self._rank = None
            self._draw()
