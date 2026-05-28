"""Team screen — create, join, and view team stats."""
from __future__ import annotations

import threading
from collections import defaultdict

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import ScrollableContainer
from textual.screen import Screen
from textual.widgets import Static
from rich.text import Text


def _fmt(n: int) -> str:
    if n >= 1_000_000:
        return f"{n / 1_000_000:.2f}M"
    if n >= 1_000:
        return f"{n / 1_000:.1f}K"
    return f"{n:,}"


def _trunc(s: str, w: int) -> str:
    return s[:w] if len(s) > w else s


def _aggregate(members: list[dict], stats: list[dict]) -> list[dict]:
    """Aggregate team_stats rows per member.

    Returns a list of dicts sorted by total tokens descending:
        user_token, pseudonym, role, tokens, prompts, cache_pct, model
    """
    # Build lookup: user_token -> pseudonym, role
    member_info: dict[str, dict] = {}
    for m in members:
        tok = m.get("user_token", "")
        member_info[tok] = {
            "pseudonym": m.get("pseudonym", "?"),
            "role":      m.get("role", "member"),
        }

    per_member: dict[str, dict] = {}
    for row in stats:
        tok = row.get("user_token", "")
        if not tok:
            continue
        if tok not in per_member:
            per_member[tok] = {
                "tokens_in":  0,
                "tokens_out": 0,
                "tokens_cache": 0,
                "prompts":    0,
                "models":     [],
            }
        d = per_member[tok]
        d["tokens_in"]    += int(row.get("tokens_input",  0) or 0)
        d["tokens_out"]   += int(row.get("tokens_output", 0) or 0)
        d["tokens_cache"] += int(row.get("tokens_cache",  0) or 0)
        d["prompts"]      += int(row.get("prompt_count",  0) or 0)
        model = row.get("favourite_model", "")
        if model:
            d["models"].append(model)

    # Include members who have no stats rows yet
    for tok in member_info:
        if tok not in per_member:
            per_member[tok] = {
                "tokens_in": 0, "tokens_out": 0,
                "tokens_cache": 0, "prompts": 0, "models": [],
            }

    result = []
    for tok, d in per_member.items():
        total   = d["tokens_in"] + d["tokens_out"] + d["tokens_cache"]
        cache   = d["tokens_cache"]
        cache_pct = round(100 * cache / total, 1) if total > 0 else 0.0
        # Most common model in the period
        model = ""
        if d["models"]:
            from collections import Counter
            model = Counter(d["models"]).most_common(1)[0][0]
        info = member_info.get(tok, {"pseudonym": tok[:8], "role": "member"})
        result.append({
            "user_token": tok,
            "pseudonym":  info["pseudonym"],
            "role":       info["role"],
            "tokens":     total,
            "prompts":    d["prompts"],
            "cache_pct":  cache_pct,
            "model":      model,
        })

    result.sort(key=lambda r: r["tokens"], reverse=True)
    return result


class _Header(Static):
    DEFAULT_CSS = "_Header { height: 1; background: #12122a; color: #7a7a9a; padding: 0 2; }"


class _Footer(Static):
    DEFAULT_CSS = "_Footer { height: 1; background: #12122a; color: #555577; padding: 0 2; }"

    def render(self) -> str:
        return "c create   j join   l leave   r refresh   s sync code   Esc back"


class TeamScreen(Screen):
    """Team features — create, join, view member stats."""

    BINDINGS = [
        Binding("escape", "app.pop_screen", "Back",    show=False),
        Binding("r",      "refresh",        "refresh", show=False),
        Binding("c",      "create_team",    "create",  show=False),
        Binding("j",      "join_team",      "join",    show=False),
        Binding("l",      "leave_team",     "leave",   show=False),
        Binding("s",      "show_sync_code", "sync",    show=False),
    ]

    DEFAULT_CSS = """
    TeamScreen { background: #0d0d1a; }
    TeamScreen ScrollableContainer { height: 1fr; }
    """

    def __init__(self, store) -> None:
        super().__init__()
        self._store    = store
        self._members: list[dict] = []
        self._stats:   list[dict] = []
        self._loading  = True
        self._error:   str = ""

    # ------------------------------------------------------------------
    # Compose
    # ------------------------------------------------------------------

    def compose(self) -> ComposeResult:
        yield _Header("ccspy  ·  teams  ·  0 members  ·  last 7 days", id="team-header")
        yield ScrollableContainer(Static("", id="team-body"), id="team-scroll")
        yield _Footer()

    def on_mount(self) -> None:
        self.query_one("#team-scroll", ScrollableContainer).can_focus = False
        self._draw()
        self.action_refresh()

    # ------------------------------------------------------------------
    # Header update
    # ------------------------------------------------------------------

    def _update_header(self) -> None:
        from ccspy import team
        name = team.get_team_name() or "teams"
        n    = len(self._members)
        self.query_one("#team-header", _Header).update(
            f"ccspy  ·  {name}  ·  {n} member{'s' if n != 1 else ''}  ·  last 7 days"
        )

    # ------------------------------------------------------------------
    # Data loading
    # ------------------------------------------------------------------

    def action_refresh(self) -> None:
        self._loading = True
        self._draw()
        threading.Thread(target=self._fetch_data, daemon=True).start()

    def _fetch_data(self) -> None:
        from ccspy import team, identity
        try:
            if identity.is_registered() and team.is_in_team():
                team_id = team.get_team_id()
                self._members = team.fetch_members(team_id)
                self._stats   = team.fetch_stats(team_id, days=7)
            else:
                self._members = []
                self._stats   = []
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
        from ccspy import identity, team

        self._update_header()

        t = Text()
        t.append("\n")
        t.append("  CCSPY TEAMS\n", style="bold white")
        t.append("  Collaborate and compare stats with your team\n\n", style="dim #7a7a9a")

        if not identity.is_registered():
            t.append("  You need an identity to use teams.\n", style="dim #7a7a9a")
            t.append("  Press i to register.\n", style="#9999cc")
        elif not team.is_in_team():
            if self._loading:
                t.append("  Loading…\n", style="dim #7a7a9a")
            else:
                t.append("  You are not in a team.\n\n", style="dim #7a7a9a")
                t.append("  c  create a new team\n", style="#9999cc")
                t.append("  j  join an existing team by name\n", style="#9999cc")
        else:
            self._draw_team(t)

        if self._error:
            t.append(f"\n  Network error: {self._error}\n", style="dim #cc4444")

        self.query_one("#team-body", Static).update(t)

    def _draw_team(self, t: Text) -> None:
        from ccspy import identity, team

        my_token = identity.get_user_token()
        agg      = _aggregate(self._members, self._stats)

        if self._loading and not agg:
            t.append("  Loading team data…\n", style="dim #7a7a9a")
            return

        # Column widths
        W_MEMBER  = 16
        W_TOKENS  = 10
        W_MODEL   = 14
        W_PROMPTS =  8
        W_CACHE   =  6

        # Header row
        t.append("  ")
        t.append(f"{'Member':<{W_MEMBER}}  ", style="bold #9999cc")
        t.append(f"{'Tokens 7d':>{W_TOKENS}}  ", style="bold #9999cc")
        t.append(f"{'Model':<{W_MODEL}}  ", style="bold #9999cc")
        t.append(f"{'Prompts/d':>{W_PROMPTS}}  ", style="bold #9999cc")
        t.append(f"{'Cache%':>{W_CACHE}}\n", style="bold #9999cc")
        t.append("  " + "─" * (W_MEMBER + W_TOKENS + W_MODEL + W_PROMPTS + W_CACHE + 10) + "\n",
                 style="dim #2d2d4e")

        total_tokens  = 0
        total_prompts = 0

        for row in agg:
            is_me  = row["user_token"] == my_token
            name   = row["pseudonym"]
            prefix = "▶ " if is_me else "  "
            display_name = _trunc(prefix + name, W_MEMBER)
            tok    = row["tokens"]
            model  = _trunc(row["model"] or "─", W_MODEL)
            prompts_per_day = round(row["prompts"] / 7, 1) if row["prompts"] else 0.0
            cache  = f"{row['cache_pct']:.0f}%"

            style = "bold white" if is_me else "#7a7a9a"
            t.append("  ")
            t.append(f"{display_name:<{W_MEMBER}}  ", style=style)
            t.append(f"{_fmt(tok):>{W_TOKENS}}  ", style=style)
            t.append(f"{model:<{W_MODEL}}  ", style=style)
            t.append(f"{prompts_per_day:>{W_PROMPTS}.1f}  ", style=style)
            t.append(f"{cache:>{W_CACHE}}\n", style=style)

            total_tokens  += tok
            total_prompts += row["prompts"]

        # TOTAL row
        t.append("  " + "─" * (W_MEMBER + W_TOKENS + W_MODEL + W_PROMPTS + W_CACHE + 10) + "\n",
                 style="dim #2d2d4e")
        total_ppd = round(total_prompts / 7, 1) if total_prompts else 0.0
        t.append("  ")
        t.append(f"{'TOTAL':<{W_MEMBER}}  ", style="bold #9999cc")
        t.append(f"{_fmt(total_tokens):>{W_TOKENS}}  ", style="bold #9999cc")
        t.append(f"{'':{'<'}{W_MODEL}}  ", style="bold #9999cc")
        t.append(f"{total_ppd:>{W_PROMPTS}.1f}  ", style="bold #9999cc")
        t.append(f"{'':>{W_CACHE}}\n", style="bold #9999cc")

    # ------------------------------------------------------------------
    # Identity helpers
    # ------------------------------------------------------------------

    def _ensure_identity(self, then) -> None:
        from ccspy import identity
        if identity.is_registered():
            then()
        else:
            from ccspy.ui.optin_modal import OptInModal
            self.app.push_screen(OptInModal(), lambda p: self._after_register(p, then))

    def _after_register(self, pseudonym, then) -> None:
        if not pseudonym:
            return
        from ccspy import identity
        claim_code = identity.register(pseudonym)
        self.notify(
            f"Sync code: {claim_code} — save this, it cannot be recovered!",
            title="ccspy identity",
            timeout=15,
        )
        then()

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------

    def action_create_team(self) -> None:
        self._ensure_identity(self._do_create_team)

    def _do_create_team(self) -> None:
        from ccspy import team
        if team.is_in_team():
            self.notify("You are already in a team. Leave first.", title="ccspy teams")
            return

        def _create() -> None:
            result = team.create_team()
            if result:
                team_id, name = result
                self.call_from_thread(
                    lambda: self.notify(f'Created team "{name}"', title="ccspy teams")
                )
                self.call_from_thread(self.action_refresh)
            else:
                self.call_from_thread(
                    lambda: self.notify("Failed to create team.", title="ccspy teams", severity="error")
                )

        threading.Thread(target=_create, daemon=True).start()

    def action_join_team(self) -> None:
        self._ensure_identity(self._do_join_team)

    def _do_join_team(self) -> None:
        from ccspy.ui.join_team_modal import JoinTeamModal
        self.app.push_screen(JoinTeamModal(), self._handle_join)

    def _handle_join(self, name: str | None) -> None:
        if not name:
            return
        from ccspy import team

        def _join() -> None:
            ok = team.join_team(name)
            if ok:
                self.call_from_thread(
                    lambda: self.notify(f'Joined team "{name}"', title="ccspy teams")
                )
                self.call_from_thread(self.action_refresh)
            else:
                self.call_from_thread(
                    lambda: self.notify(
                        f'Team "{name}" not found.', title="ccspy teams", severity="error"
                    )
                )

        threading.Thread(target=_join, daemon=True).start()

    def action_leave_team(self) -> None:
        from ccspy import team
        if not team.is_in_team():
            self.notify("You are not in a team.", title="ccspy teams")
            return

        def _leave() -> None:
            ok = team.leave_team()
            msg = "Left team." if ok else "Failed to leave team."
            self.call_from_thread(
                lambda: self.notify(msg, title="ccspy teams")
            )
            self.call_from_thread(self._draw)

        threading.Thread(target=_leave, daemon=True).start()

    def action_show_sync_code(self) -> None:
        from ccspy import identity
        if not identity.is_registered():
            self.notify("Not registered yet.", title="ccspy")
            return
        code = identity.get_claim_code()
        if not code:
            self.notify(
                "No sync code — you may have registered before this feature was added.",
                title="ccspy",
            )
            return
        self.notify(
            f"Your sync code: {code}",
            title="ccspy identity",
            timeout=15,
        )
