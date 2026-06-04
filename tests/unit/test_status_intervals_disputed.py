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
