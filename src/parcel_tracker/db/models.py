"""Domain models: Parcel, TrackingEvent, ShipmentStatus."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum


class ShipmentStatus(Enum):
    """Canonical shipment status values."""

    NOT_FOUND = "NotFound"
    INFO_RECEIVED = "InfoReceived"
    PICKUP = "Pickup"
    IN_TRANSIT = "InTransit"
    OUT_FOR_DELIVERY = "OutForDelivery"
    CUSTOMS = "Customs"
    DELIVERED = "Delivered"
    UNDELIVERED = "Undelivered"
    EXCEPTION = "Exception"
    RETURNED = "Returned"
    EXPIRED = "Expired"
    ALERT = "Alert"

    @classmethod
    def from_str(cls, raw: str | None) -> ShipmentStatus:
        """Coerce a string to a ShipmentStatus, defaulting to NOT_FOUND."""
        if not raw:
            return cls.NOT_FOUND
        for member in cls:
            if member.value == raw:
                return member
        return cls.NOT_FOUND


@dataclass(slots=True)
class TrackingEvent:
    """A single event in the tracking history."""

    time: str
    description: str
    location: str | None = None
    carrier: str | None = None


@dataclass(slots=True)
class Parcel:
    """A tracked parcel record."""

    tracking_number: str
    user_id: int
    name: str | None = None
    carrier_code: str | None = None
    carrier_name: str | None = None
    all_carriers: list[str] = field(default_factory=list)
    status: ShipmentStatus = ShipmentStatus.NOT_FOUND
    last_event: str | None = None
    last_event_time: str | None = None
    events: list[TrackingEvent] = field(default_factory=list)
    origin: str | None = None
    destination: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None
    delivered_at: datetime | None = None
    is_active: bool = True
