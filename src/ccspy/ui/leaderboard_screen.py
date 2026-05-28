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
        from ccspy import leaderboard as lb, identity, team

        try:
            top  = lb.fetch_top(10)
            peak = lb.peak_day_tokens(self._store)
            rank = None
            if lb.is_opted_in():
                lb.push_score(self._store)
                rank = lb.fetch_rank(identity.get_user_token(), peak)
            lb.save_cache(top, rank, peak)
            self._top   = top
            self._rank  = rank
            self._peak  = peak
            self._error = ""

            # Also push team stats if in a team
            try:
                if team.is_in_team():
                    team.push_stats(self._store)
            except Exception:
                pass
        except Exception as exc:
            self._error = str(exc)[:80]
        finally:
            self._loading = False
            self.call_from_thread(self._draw)

    # ------------------------------------------------------------------
    # Rendering
    # ------------------------------------------------------------------

    def _draw(self) -> None:
        from ccspy import leaderboard as lb, identity

        opted_in  = lb.is_opted_in()
        pseudonym = identity.get_pseudonym()

        t = Text()
        t.append("\n")
        t.append("  CCSPY LEADERBOARD\n", style="bold white")
        t.append("  Peak tokens consumed in a single day\n\n", style="dim #7a7a9a")

        if self._loading and not self._top:
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

        def _name(entry: dict | None, inner: int) -> str:
            if not entry:
                return "─" * min(4, inner - 2)
            return _trunc(entry.get("pseudonym", "?"), inner - 2)

        def _score_str(entry: dict | None, wide: bool) -> str:
            if not entry:
                return "─"
            n = _fmt(entry.get("peak_day", 0))
            return f"{n} tok/day" if wide else n

        def _pad(s: str, w: int) -> str:
            return f" {s:<{w - 2}} "

        def _card(medal: str, rank: int, entry: dict | None, W: int, color: str) -> list:
            bold = f"bold {color}"
            dim  = f"dim {color}"
            nm   = _name(entry, W)
            sc   = _score_str(entry, W > 14)
            return [
                (f"┌{'─' * W}┐",                     bold),
                (f"│{_pad(f'{medal}  #{rank}', W)}│", bold),
                (f"│{_pad(nm, W)}│",                  bold),
                (f"│{_pad(sc, W)}│",                  color),
                (f"└{'─' * W}┘",                      dim),
            ]

        gold_c   = _card("★", 1, e1, _CW, _GOLD)
        silver_c = _card("✦", 2, e2, _SW, _SILVER)
        bronze_c = _card("·", 3, e3, _SW, _BRONZE)

        g_ped = ("█" * (_CW + 2), _GOLD)
        s_ped = ("█" * (_SW + 2), _SILVER)
        b_ped = ("█" * (_SW + 2), _BRONZE)
        blank = (" " * (_SW + 2), "")

        def _a(seg: tuple) -> None:
            t.append(seg[0], style=seg[1] or None)

        # Stepped podium (8 rows):
        #   gold   (#1): rows 0–4 card, rows 5–7 pedestal  ← highest
        #   silver (#2): rows 1–5 card, rows 6–7 pedestal
        #   bronze (#3): rows 2–6 card, row  7   pedestal  ← lowest
        for row in range(8):
            t.append(_IND)

            # Left — silver (#2)
            if row == 0:
                _a(blank)
            elif row <= 5:
                _a(silver_c[row - 1])
            else:
                _a(s_ped)

            t.append(_GAP)

            # Centre — gold (#1)
            if row <= 4:
                _a(gold_c[row])
            else:
                _a(g_ped)

            t.append(_GAP)

            # Right — bronze (#3)
            if row <= 1:
                _a(blank)
            elif row <= 6:
                _a(bronze_c[row - 2])
            else:
                _a(b_ped)

            t.append("\n")

        t.append("\n")

    def _draw_rest(self, t: Text) -> None:
        rest = self._top[3:]
        if not rest:
            return
        t.append("  ─────────────────────────────────────────────────────\n", style="dim #2d2d4e")
        for i, entry in enumerate(rest, start=4):
            name  = _trunc(entry.get("pseudonym", "?"), 20)
            score = _fmt(entry.get("peak_day", 0))
            t.append(f"  #{i:<3} ", style="dim #555577")
            t.append(f"{name:<22}", style="#7a7a9a")
            t.append(f"{score:>10} tok/day\n", style="dim #555577")

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------

    def action_optin_flow(self) -> None:
        from ccspy import identity, leaderboard as lb
        from ccspy.ui.optin_modal import OptInModal

        if not identity.is_registered():
            # Need to register first
            self.app.push_screen(OptInModal(), self._handle_register_then_optin)
        else:
            # Already registered — update pseudonym on leaderboard or just opt in
            current = identity.get_pseudonym() if lb.is_opted_in() else ""
            self.app.push_screen(OptInModal(current=current), self._handle_optin_only)

    def _handle_register_then_optin(self, pseudonym: str | None) -> None:
        if not pseudonym:
            return
        from ccspy import identity, leaderboard as lb
        claim_code = identity.register(pseudonym)
        lb.opt_in()
        self.notify(
            f"Sync code: {claim_code} — save this, it cannot be recovered!",
            title="ccspy identity",
            timeout=15,
        )
        self.notify(f'Joined leaderboard as "{pseudonym}"', title="ccspy leaderboard")
        self.action_refresh()

    def _handle_optin_only(self, pseudonym: str | None) -> None:
        if not pseudonym:
            return
        from ccspy import leaderboard as lb
        lb.opt_in()
        self.notify(f'Joined as "{pseudonym}"', title="ccspy leaderboard")
        self.action_refresh()

    def action_optout(self) -> None:
        from ccspy import leaderboard as lb, identity
        if lb.is_opted_in():
            name = identity.get_pseudonym()
            lb.opt_out()
            self.notify(f'Removed "{name}" from leaderboard', title="ccspy")
            self._rank = None
            self._draw()
