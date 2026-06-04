from datetime import UTC, datetime, timedelta

from parcel_tracker.core.status_intervals import is_due
from parcel_tracker.db.models import ShipmentStatus


def test_delivered_not_due_normally() -> None:
    now = datetime(2026, 6, 4, 12, 0, tzinfo=UTC)
    assert is_due(ShipmentStatus.DELIVERED, now - timedelta(days=1), now) is False


def test_delivered_disputed_is_due() -> None:
    now = datetime(2026, 6, 4, 12, 0, tzinfo=UTC)
    last = now - timedelta(hours=2)
    assert is_due(ShipmentStatus.DELIVERED, last, now, delivery_disputed=True) is True


def test_disputed_stops_after_grace_window() -> None:
    now = datetime(2026, 6, 4, 12, 0, tzinfo=UTC)
    old_delivery = now - timedelta(hours=100)  # past the 72h grace
    assert (
        is_due(
            ShipmentStatus.DELIVERED,
            now - timedelta(hours=2),
            now,
            delivery_disputed=True,
            delivered_at=old_delivery,
        )
        is False
    )


def test_disputed_within_grace_still_due() -> None:
    now = datetime(2026, 6, 4, 12, 0, tzinfo=UTC)
    recent_delivery = now - timedelta(hours=5)
    assert (
        is_due(
            ShipmentStatus.DELIVERED,
            now - timedelta(hours=2),
            now,
            delivery_disputed=True,
            delivered_at=recent_delivery,
        )
        is True
    )
