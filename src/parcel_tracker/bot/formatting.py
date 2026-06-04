"""Presentation helpers: human-readable event times and localized status labels."""

from __future__ import annotations

from datetime import datetime

from parcel_tracker.db.models import ShipmentStatus
from parcel_tracker.i18n import _

_DATE_ONLY_LEN = 10  # "YYYY-MM-DD"


def fmt_event_time(raw: str | None) -> str:
    """Format a carrier-provided timestamp as 'dd/mm/YYYY HH:MM'.

    Accepts ISO 8601 (with or without tz offset / 'Z'), 'YYYY-MM-DD HH:MM:SS',
    or date-only 'YYYY-MM-DD'. Returns the (stripped) raw string unchanged when
    it cannot be parsed, so we never crash on an unexpected carrier format.
    """
    if not raw:
        return ""
    text = raw.strip()
    iso = text.replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(iso)
    except ValueError:
        return text
    if len(text) <= _DATE_ONLY_LEN and "T" not in text and ":" not in text:
        return dt.strftime("%d/%m/%Y")
    return dt.strftime("%d/%m/%Y %H:%M")


_STATUS_MSGID: dict[ShipmentStatus, str] = {
    ShipmentStatus.NOT_FOUND: "Not found",
    ShipmentStatus.INFO_RECEIVED: "Info received",
    ShipmentStatus.PICKUP: "Picked up",
    ShipmentStatus.IN_TRANSIT: "In transit",
    ShipmentStatus.OUT_FOR_DELIVERY: "Out for delivery",
    ShipmentStatus.CUSTOMS: "In customs",
    ShipmentStatus.DELIVERED: "Delivered",
    ShipmentStatus.UNDELIVERED: "Undelivered",
    ShipmentStatus.EXCEPTION: "Exception",
    ShipmentStatus.RETURNED: "Returned",
    ShipmentStatus.EXPIRED: "Expired",
    ShipmentStatus.ALERT: "Alert",
}


def status_label(status: ShipmentStatus) -> str:
    """Human, translatable label for a status (falls back to the enum value)."""
    return _(_STATUS_MSGID.get(status, status.value))
