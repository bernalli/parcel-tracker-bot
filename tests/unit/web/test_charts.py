"""Inline SVG built server-side: every text value is escaped, icons are constants."""

from __future__ import annotations

import pytest

from parcel_tracker.web.charts import Series, grouped_columns, nice_scale
from parcel_tracker.web.render import icon

HOSTILE = '"><script>alert(1)</script>'


def test_chart_escapes_every_text_value() -> None:
    svg = str(
        grouped_columns(
            [f"2026-10-05{HOSTILE}"],
            [HOSTILE],
            [Series(label=HOSTILE, css_class=f"s1{HOSTILE}", values=[3])],
            aria_label=HOSTILE,
        )
    )
    assert HOSTILE not in svg
    assert "<script" not in svg
    # Each of the five values arrives escaped, quote included.
    assert svg.count("&#34;&gt;&lt;script&gt;") >= 5


def test_icon_never_echoes_its_name() -> None:
    assert str(icon(HOSTILE)) == str(icon("pending"))
    assert "script" not in str(icon(HOSTILE))


@pytest.mark.parametrize(
    ("value", "expected"),
    [(0, (1, 1)), (7, (8, 2)), (10, (10, 2)), (23, (25, 5)), (180, (200, 50))],
)
def test_nice_scale(value: int, expected: tuple[int, int]) -> None:
    assert nice_scale(value) == expected
