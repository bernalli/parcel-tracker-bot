"""Tests for ShipmentStatus → interval mapping + is_due()."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from parcel_tracker.core.status_intervals import (
    DEFAULT_INTERVALS_MIN,
    get_interval_minutes,
    is_due,
)
from parcel_tracker.db.models import ShipmentStatus


def test_default_intervals_cover_all_statuses() -> None:
    for status in ShipmentStatus:
        assert status in DEFAULT_INTERVALS_MIN, f"missing {status}"


def test_get_interval_returns_zero_for_delivered() -> None:
    assert get_interval_minutes(ShipmentStatus.DELIVERED) == 0


def test_get_interval_returns_zero_for_expired() -> None:
    assert get_interval_minutes(ShipmentStatus.EXPIRED) == 0


def test_get_interval_out_for_delivery_high_freshness() -> None:
    assert get_interval_minutes(ShipmentStatus.OUT_FOR_DELIVERY) == 5


def test_is_due_false_when_status_zero_interval() -> None:
    now = datetime(2026, 5, 9, 12, 0, tzinfo=UTC)
    last = datetime(2026, 5, 9, 11, 0, tzinfo=UTC)
    assert is_due(ShipmentStatus.DELIVERED, last, now) is False
    assert is_due(ShipmentStatus.EXPIRED, last, now) is False


def test_is_due_true_when_no_last_check_at() -> None:
    now = datetime(2026, 5, 9, 12, 0, tzinfo=UTC)
    assert is_due(ShipmentStatus.IN_TRANSIT, None, now) is True


def test_is_due_true_when_interval_elapsed() -> None:
    now = datetime(2026, 5, 9, 12, 0, tzinfo=UTC)
    last = now - timedelta(minutes=20)  # IN_TRANSIT interval = 15 min
    assert is_due(ShipmentStatus.IN_TRANSIT, last, now) is True


def test_is_due_false_when_interval_not_elapsed() -> None:
    now = datetime(2026, 5, 9, 12, 0, tzinfo=UTC)
    last = now - timedelta(minutes=10)  # IN_TRANSIT interval = 15 min
    assert is_due(ShipmentStatus.IN_TRANSIT, last, now) is False


def test_is_due_boundary_inclusive() -> None:
    now = datetime(2026, 5, 9, 12, 0, tzinfo=UTC)
    last = now - timedelta(minutes=15)  # exactly the interval
    assert is_due(ShipmentStatus.IN_TRANSIT, last, now) is True
