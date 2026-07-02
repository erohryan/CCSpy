"""Shared formatting helpers for dashboard widgets."""
from __future__ import annotations

from rich.text import Text

SPARK_CHARS = " ▁▂▃▄▅▆▇█"
BAR_CHAR = "█"
TOOL_BAR_CHAR = "▓"

# Colour palette for stacked proportion bars (cycles if more slices than colours)
SLICE_COLORS = [
    "#2ac3de",  # cyan
    "#c678dd",  # magenta
    "#e0823a",  # orange
    "#44cf6c",  # green
    "#9999cc",  # lavender
    "#cc6644",  # terracotta
    "#de9a26",  # amber
    "#7eb8c9",  # steel blue
]

MODEL_SHORT_NAMES: dict[str, str] = {
    "claude-sonnet-5": "Sonnet 5",
    "claude-fable-5": "Fable 5",
    "claude-mythos-5": "Mythos 5",
    "claude-opus-4-8": "Opus 4.8",
    "claude-opus-4-7": "Opus 4.7",
    "claude-opus-4-6": "Opus 4.6",
    "claude-opus-4-5-20251101": "Opus 4.5",
    "claude-opus-4-1-20250805": "Opus 4.1",
    "claude-opus-4-20250514": "Opus 4",
    "claude-sonnet-4-6": "Sonnet 4.6",
    "claude-sonnet-4-5-20250929": "Sonnet 4.5",
    "claude-sonnet-4-20250514": "Sonnet 4",
    "claude-haiku-4-5-20251001": "Haiku 4.5",
    "claude-haiku-3-5-20241022": "Haiku 3.5",
    "<synthetic>": "<synthetic>",
}


def short_model(model_id: str) -> str:
    if model_id in MODEL_SHORT_NAMES:
        return MODEL_SHORT_NAMES[model_id]
    m = model_id.replace("claude-", "")
    parts = m.rsplit("-", 1)
    if len(parts) == 2 and parts[1].isdigit() and len(parts[1]) == 8:
        m = parts[0]
    return m.replace("-", " ").title()


def fmt_tokens(n: int) -> str:
    if n >= 1_000_000:
        return f"{n / 1_000_000:.1f}M"
    if n >= 1_000:
        return f"{n / 1_000:.0f}K"
    return str(n)


def fmt_cost(cost: float | None) -> str:
    if cost is None:
        return "—"
    if cost >= 1000:
        return f"${cost:,.0f}"
    if cost >= 100:
        return f"${cost:.0f}"
    return f"${cost:.2f}"


def fmt_pct(pct: float) -> str:
    """Right-align percentage with dot-padding as the spec requires."""
    s = f"{pct:.1f}%"
    return s.rjust(6, "·")  # · padding


def spark(values: list[int], width: int | None = None) -> str:
    """Render a sparkline from a list of values."""
    if not values:
        return ""
    if width is not None:
        # Sample or pad to exactly `width` slots
        if len(values) > width:
            values = values[-width:]
        elif len(values) < width:
            values = [0] * (width - len(values)) + values
    mx = max(values) if values else 0
    if mx == 0:
        return SPARK_CHARS[0] * len(values)
    return "".join(SPARK_CHARS[min(8, int(v / mx * 8))] for v in values)


def bar(pct: float, width: int = 16, char: str = BAR_CHAR) -> str:
    """Render a horizontal bar of given width proportional to pct (0-100)."""
    filled = max(0, round(pct / 100 * width))
    return char * filled


def stacked_bar(
    items: list[tuple[str, float]],
    width: int = 34,
    colors: list[str] | None = None,
) -> Text:
    """Single proportional bar where each slice is a differently-coloured segment.

    items: [(label, pct), ...] where pct is 0–100 and slices need not sum to 100.
    Remaining space (if pcts < 100) is left as empty chars so the bar always
    fills `width` characters.
    """
    t = Text()
    if not items:
        return t
    palette = colors or SLICE_COLORS
    total = sum(pct for _, pct in items)
    if total == 0:
        return t

    allocated = 0
    for i, (_, pct) in enumerate(items):
        is_last = i == len(items) - 1
        chars = (width - allocated) if is_last else max(0, round(pct / 100 * width))
        chars = min(chars, width - allocated)
        if chars > 0:
            t.append(BAR_CHAR * chars, style=palette[i % len(palette)])
        allocated += chars

    return t


def delta_str(current: int, previous: int) -> str:
    """Return '▲ 18%' or '▼ 5%' comparing current to previous period."""
    if previous == 0:
        return ""
    pct = (current - previous) / previous * 100
    arrow = "▲" if pct >= 0 else "▼"
    return f"{arrow} {abs(pct):.0f}%"


def age_str(seconds: float) -> str:
    """Human-readable duration: '3m', '12s', '1h 4m'."""
    seconds = int(seconds)
    if seconds < 60:
        return f"{seconds}s"
    m = seconds // 60
    if m < 60:
        return f"{m}m"
    h = m // 60
    rm = m % 60
    return f"{h}h {rm}m"


def fmt_duration(secs: float) -> str:
    """Format seconds as a compact human-readable duration."""
    if secs < 60:
        return f"{secs:.0f}s"
    m = int(secs / 60)
    s = int(secs % 60)
    if m < 60:
        return f"{m}m {s}s" if s else f"{m}m"
    h = m // 60
    rm = m % 60
    return f"{h}h {rm}m" if rm else f"{h}h"
