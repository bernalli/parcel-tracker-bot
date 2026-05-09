"""Tests for src/parcel_tracker/db/models.py."""

from __future__ import annotations

from datetime import UTC, datetime

from parcel_tracker.db.models import (
    Parcel,
    ShipmentStatus,
    TrackingEvent,
)


def test_shipment_status_enum_values() -> None:
    assert ShipmentStatus.NOT_FOUND.value == "NotFound"
    assert ShipmentStatus.IN_TRANSIT.value == "InTransit"
    assert ShipmentStatus.DELIVERED.value == "Delivered"
    # Round-trip via .from_str
    assert ShipmentStatus.from_str("Delivered") is ShipmentStatus.DELIVERED
    assert ShipmentStatus.from_str("unknown_status") is ShipmentStatus.NOT_FOUND


def test_tracking_event_dataclass() -> None:
    event = TrackingEvent(
        time="2026-05-09 10:30:00",
        description="Out for delivery",
        location="Milano",
    )
    assert event.time == "2026-05-09 10:30:00"
    assert event.location == "Milano"


def test_parcel_dataclass_defaults() -> None:
    parcel = Parcel(
        tracking_number="ABC123",
        user_id=42,
    )
    assert parcel.status is ShipmentStatus.NOT_FOUND
    assert parcel.is_active is True
    assert parcel.events == []
    assert parcel.all_carriers == []


def test_parcel_round_trip_status() -> None:
    parcel = Parcel(
        tracking_number="X",
        user_id=1,
        status=ShipmentStatus.DELIVERED,
        delivered_at=datetime(2026, 5, 1, 12, 0, tzinfo=UTC),
    )
    assert parcel.status is ShipmentStatus.DELIVERED
