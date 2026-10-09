"""Dashboard statistics."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

from parcel_tracker.core.shipments import StatusGroup
from parcel_tracker.core.stats import compute_stats, delivery_days
from parcel_tracker.db.models import Parcel, ShipmentStatus

NOW = datetime(2026, 10, 9, 12, 0, tzinfo=UTC)  # a Friday


def _p(  # noqa: PLR0913
    code: str,
    status: ShipmentStatus,
    *,
    added_days_ago: float,
    delivered_after: float | None = None,
    carrier: str = "DHL",
    active: bool = True,
    quiet_days: float = 0,
) -> Parcel:
    created = NOW - timedelta(days=added_days_ago)
    return Parcel(
        tracking_number=code,
        user_id=1,
        status=status,
        carrier_name=carrier,
        is_active=active,
        created_at=created,
        last_change_at=NOW - timedelta(days=quiet_days),
        delivered_at=created + timedelta(days=delivered_after)
        if delivered_after is not None
        else None,
    )


def test_compute_stats() -> None:
    parcels = [
        _p("A", ShipmentStatus.DELIVERED, added_days_ago=10, delivered_after=2, active=False),
        _p("B", ShipmentStatus.DELIVERED, added_days_ago=5, delivered_after=4, carrier="UPS"),
        _p("C", ShipmentStatus.IN_TRANSIT, added_days_ago=8, quiet_days=7),
        _p("D", ShipmentStatus.EXCEPTION, added_days_ago=3, carrier="UPS"),
        _p("E", ShipmentStatus.NOT_FOUND, added_days_ago=1),
        _p("F", ShipmentStatus.IN_TRANSIT, added_days_ago=200, active=False),
    ]
    stats = compute_stats(parcels, now=NOW, stall_days=5, weeks=4)
    assert stats.total == 6
    assert stats.active == 4
    assert stats.by_group[StatusGroup.TRANSIT] == 1
    assert stats.by_group[StatusGroup.ATTENTION] == 1
    assert stats.by_group[StatusGroup.PENDING] == 1
    assert stats.by_group[StatusGroup.DELIVERED] == 1
    assert stats.stalled == 1
    assert stats.attention == 2  # stalled C + exception D
    assert stats.shipped_recent == 5
    assert stats.delivered_recent == 2
    assert stats.median_delivery_days == 3.0
    assert stats.p90_delivery_days == 4.0
    assert stats.delivery_rate == 2 / 3
    assert [w.week_start for w in stats.weekly] == [
        date(2026, 9, 14),
        date(2026, 9, 21),
        date(2026, 9, 28),
        date(2026, 10, 5),
    ]
    assert sum(w.shipped for w in stats.weekly) == 5
    carriers = {c.carrier: c for c in stats.carriers}
    assert carriers["UPS"].issues == 1
    assert carriers["UPS"].median_days == 4.0
    assert carriers["DHL"].total == 4


def test_empty_and_negative_durations() -> None:
    stats = compute_stats([], now=NOW, stall_days=5)
    assert stats.median_delivery_days is None
    assert stats.delivery_rate is None
    assert len(stats.weekly) == 12
    odd = Parcel(
        tracking_number="Z", user_id=1, created_at=NOW, delivered_at=NOW - timedelta(days=1)
    )
    assert delivery_days(odd) is None
