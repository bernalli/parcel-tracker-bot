"""Tests for date/status formatting helpers."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from parcel_tracker.bot import formatting
from parcel_tracker.bot.formatting import fmt_check_time, status_emoji
from parcel_tracker.db.models import ShipmentStatus


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("2026-06-04T03:45:00+02:00", "04/06/2026 03:45"),
        ("2026-06-04T05:24:00Z", "04/06/2026 05:24"),
        ("2026-06-04 05:24:00", "04/06/2026 05:24"),
        ("2026-06-04", "04/06/2026"),
    ],
)
def test_fmt_event_time_parses_known_formats(raw: str, expected: str) -> None:
    assert formatting.fmt_event_time(raw) == expected


def test_fmt_event_time_falls_back_to_raw_when_unparseable() -> None:
    assert formatting.fmt_event_time("garbage-not-a-date") == "garbage-not-a-date"


def test_fmt_event_time_empty_returns_empty() -> None:
    assert formatting.fmt_event_time(None) == ""
    assert formatting.fmt_event_time("") == ""


def test_status_label_known_status() -> None:
    # English baseline (no translator installed → gettext identity).
    assert formatting.status_label(ShipmentStatus.IN_TRANSIT) == "In transit"
    assert formatting.status_label(ShipmentStatus.OUT_FOR_DELIVERY) == "Out for delivery"
    assert formatting.status_label(ShipmentStatus.DELIVERED) == "Delivered"


def test_status_emoji_known_status() -> None:
    assert status_emoji(ShipmentStatus.IN_TRANSIT) == "🚚"
    assert status_emoji(ShipmentStatus.DELIVERED) == "✅"


def test_status_emoji_fallback_parcel() -> None:
    assert status_emoji(ShipmentStatus.NOT_FOUND) == "❓"
    # qualunque status sconosciuto degrada a 📦 (guard difensivo)
    assert status_emoji(None) == "📦"  # type: ignore[arg-type]


def test_fmt_check_time_none_is_empty() -> None:
    assert fmt_check_time(None) == ""


def test_fmt_check_time_formats_dd_mm_yyyy_hhmm() -> None:
    dt = datetime(2026, 6, 7, 10, 40, tzinfo=UTC)
    out = fmt_check_time(dt)
    assert "/2026" in out
    assert ":" in out  # ha anche l'orario
