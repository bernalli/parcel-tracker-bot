"""ShipmentStatus → check interval mapping + is_due() helper."""

from __future__ import annotations

from datetime import datetime, timedelta

from parcel_tracker.db.models import ShipmentStatus

DEFAULT_INTERVALS_MIN: dict[ShipmentStatus, int] = {
    ShipmentStatus.NOT_FOUND: 60,
    ShipmentStatus.INFO_RECEIVED: 60,
    ShipmentStatus.PICKUP: 30,
    ShipmentStatus.IN_TRANSIT: 15,
    ShipmentStatus.OUT_FOR_DELIVERY: 5,
    ShipmentStatus.CUSTOMS: 30,
    ShipmentStatus.DELIVERED: 0,
    ShipmentStatus.UNDELIVERED: 30,
    ShipmentStatus.EXCEPTION: 30,
    ShipmentStatus.RETURNED: 60,
    ShipmentStatus.EXPIRED: 0,
    ShipmentStatus.ALERT: 30,
}


DISPUTED_INTERVAL_MIN: int = 30


def get_interval_minutes(status: ShipmentStatus) -> int:
    """Return the polling interval (minutes) for a given status. 0 = stop polling."""
    return DEFAULT_INTERVALS_MIN[status]


def is_due(
    status: ShipmentStatus,
    last_check_at: datetime | None,
    now: datetime,
    *,
    delivery_disputed: bool = False,
) -> bool:
    """True if a parcel needs re-check given status, last check time, and dispute flag."""
    if status is ShipmentStatus.DELIVERED and delivery_disputed:
        interval = DISPUTED_INTERVAL_MIN
    else:
        interval = get_interval_minutes(status)
    if interval == 0:
        return False
    if last_check_at is None:
        return True
    return now >= last_check_at + timedelta(minutes=interval)
