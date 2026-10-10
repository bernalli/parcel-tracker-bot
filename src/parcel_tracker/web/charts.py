"""Server-rendered SVG charts (no JavaScript needed to draw, CSP-friendly).

Follows the dashboard's chart rules: bars at most 24px wide with a 4px rounded
data end and a square baseline, a 2px gap between touching bars, hairline grid,
clean tick values, colours from CSS classes (light/dark themes), and one hover
target per category carrying a text tooltip.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from markupsafe import Markup, escape


@dataclass(frozen=True, slots=True)
class Series:
    label: str
    css_class: str
    values: Sequence[int]


_WIDTH = 640
_HEIGHT = 220
_PAD_LEFT = 36
_PAD_RIGHT = 8
_PAD_TOP = 12
_PAD_BOTTOM = 28
_BAR_MAX = 24
_BAR_GAP = 2
_RADIUS = 4


def nice_scale(value: int) -> tuple[int, int]:
    """(axis maximum, tick step): a 1/2/5×10ⁿ step and at most five intervals."""
    value = max(value, 1)
    step = 1
    while True:
        for base in (1, 2, 5):
            candidate = base * step
            if candidate * 5 >= value:
                return -(-value // candidate) * candidate, candidate
        step *= 10


def nice_max(value: int) -> int:
    """Axis maximum for ``value``."""
    return nice_scale(value)[0]


def _bar_path(x: float, y: float, w: float, h: float) -> str:
    """A column with rounded top corners and a square base."""
    if h <= 0:
        return ""
    r = min(_RADIUS, w / 2, h)
    return (
        f"M{x:.1f},{y + h:.1f} V{y + r:.1f} Q{x:.1f},{y:.1f} {x + r:.1f},{y:.1f} "
        f"H{x + w - r:.1f} Q{x + w:.1f},{y:.1f} {x + w:.1f},{y + r:.1f} V{y + h:.1f} Z"
    )


def grouped_columns(
    categories: Sequence[str],
    category_titles: Sequence[str],
    series: Sequence[Series],
    *,
    aria_label: str,
) -> Markup:
    """Grouped column chart. ``categories`` are ISO dates rendered as x labels."""
    plot_w = _WIDTH - _PAD_LEFT - _PAD_RIGHT
    plot_h = _HEIGHT - _PAD_TOP - _PAD_BOTTOM
    top, step = nice_scale(max((max(s.values, default=0) for s in series), default=0))
    band = plot_w / max(1, len(categories))
    bar = min(_BAR_MAX, (band * 0.7 - _BAR_GAP * (len(series) - 1)) / max(1, len(series)))
    group_w = bar * len(series) + _BAR_GAP * (len(series) - 1)
    baseline = _PAD_TOP + plot_h

    parts: list[str] = [
        f'<svg class="chart" viewBox="0 0 {_WIDTH} {_HEIGHT}" role="img" '
        f'aria-label="{escape(aria_label)}" preserveAspectRatio="xMidYMid meet">'
    ]
    for value in range(0, top + 1, step):
        y = baseline - plot_h * value / top
        parts.append(
            f'<line class="grid" x1="{_PAD_LEFT}" x2="{_WIDTH - _PAD_RIGHT}" '
            f'y1="{y:.1f}" y2="{y:.1f}"/>'
            f'<text class="tick" x="{_PAD_LEFT - 6}" y="{y + 4:.1f}" text-anchor="end">'
            f"{value}</text>"
        )
    for idx, category in enumerate(categories):
        x0 = _PAD_LEFT + band * idx + (band - group_w) / 2
        for s_idx, s in enumerate(series):
            value = s.values[idx]
            h = plot_h * value / top if top else 0
            path = _bar_path(x0 + s_idx * (bar + _BAR_GAP), baseline - h, bar, h)
            if path:
                parts.append(f'<path class="bar {escape(s.css_class)}" d="{path}"/>')
        tip = escape(category_titles[idx])
        parts.append(
            f'<rect class="hit" x="{_PAD_LEFT + band * idx:.1f}" y="{_PAD_TOP}" '
            f'width="{band:.1f}" height="{plot_h}" data-tip="{tip}" tabindex="0">'
            f"<title>{tip}</title></rect>"
        )
        if idx % 2 == len(categories) % 2 or len(categories) <= 6:  # noqa: PLR2004
            parts.append(
                f'<text class="tick xlabel" x="{_PAD_LEFT + band * (idx + 0.5):.1f}" '
                f'y="{_HEIGHT - 8}" text-anchor="middle" data-date="{escape(category)}">'
                f"{escape(category[5:])}</text>"
            )
    parts.append(
        f'<line class="axis" x1="{_PAD_LEFT}" x2="{_WIDTH - _PAD_RIGHT}" '
        f'y1="{baseline}" y2="{baseline}"/>'
    )
    parts.append("</svg>")
    return Markup("".join(parts))  # noqa: S704  # nosec B704 — escaped values only
