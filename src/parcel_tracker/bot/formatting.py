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


def _status_labels() -> dict[ShipmentStatus, str]:
    # Literal _() calls so babel extracts every label (a dynamic msgid never
    # reaches the catalogs, which left statuses in English for every user).
    return {
        ShipmentStatus.NOT_FOUND: _("Not found"),
        ShipmentStatus.INFO_RECEIVED: _("Info received"),
        ShipmentStatus.PICKUP: _("Picked up"),
        ShipmentStatus.IN_TRANSIT: _("In transit"),
        ShipmentStatus.OUT_FOR_DELIVERY: _("Out for delivery"),
        ShipmentStatus.CUSTOMS: _("In customs"),
        ShipmentStatus.DELIVERED: _("Delivered"),
        ShipmentStatus.UNDELIVERED: _("Undelivered"),
        ShipmentStatus.EXCEPTION: _("Exception"),
        ShipmentStatus.RETURNED: _("Returned"),
        ShipmentStatus.EXPIRED: _("Expired"),
        ShipmentStatus.ALERT: _("Alert"),
    }


def status_label(status: ShipmentStatus) -> str:
    """Human, translatable label for a status (falls back to the enum value)."""
    return _status_labels().get(status, status.value)


_STATUS_EMOJI: dict[ShipmentStatus, str] = {
    ShipmentStatus.NOT_FOUND: "❓",
    ShipmentStatus.INFO_RECEIVED: "ℹ️",
    ShipmentStatus.PICKUP: "📦",
    ShipmentStatus.IN_TRANSIT: "🚚",
    ShipmentStatus.OUT_FOR_DELIVERY: "🚛",
    ShipmentStatus.CUSTOMS: "🛃",
    ShipmentStatus.DELIVERED: "✅",
    ShipmentStatus.UNDELIVERED: "❌",
    ShipmentStatus.EXCEPTION: "⚠️",
    ShipmentStatus.RETURNED: "↩️",
    ShipmentStatus.EXPIRED: "⏰",
    ShipmentStatus.ALERT: "🚨",
}


def status_emoji(status: ShipmentStatus) -> str:
    """Emoji for a status; defensive 📦 fallback for unknown values."""
    return _STATUS_EMOJI.get(status, "📦")


def fmt_check_time(dt: datetime | None) -> str:
    """Format a last-check datetime as 'dd/mm/YYYY HH:MM' in local time ('' when None)."""
    if dt is None:
        return ""
    local = dt.astimezone() if dt.tzinfo is not None else dt
    return local.strftime("%d/%m/%Y %H:%M")
