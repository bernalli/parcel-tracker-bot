"""Tests for date/status formatting helpers."""

from __future__ import annotations

import pytest

from parcel_tracker.bot import formatting
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
