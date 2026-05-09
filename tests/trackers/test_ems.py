"""Tests for EmsTracker (Tier D)."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from parcel_tracker.core.tracker_base import TrackingResult
from parcel_tracker.db.models import ShipmentStatus, TrackingEvent
from parcel_tracker.trackers.ems import EmsTracker
from parcel_tracker.trackers.track17 import Track17Tracker


@pytest.mark.parametrize(
    "tracking_id,expected_match",
    [
        ("EE123456789CN", True),
        ("EM987654321JP", True),
        ("LX123456789CN", False),
        ("RR987654321DE", False),
        ("", False),
    ],
)
def test_ems_detection(tracking_id: str, expected_match: bool) -> None:
    tracker = EmsTracker()
    assert tracker.detect(tracking_id) is expected_match


async def test_ems_returns_not_found_without_track17() -> None:
    tracker = EmsTracker(track17=None)
    result = await tracker.fetch("EE123456789CN")
    assert not result.found
    assert result.carrier_name == "EMS"
    assert result.carrier_code == "ems"


async def test_ems_delegates_and_rebrands() -> None:
    track17_mock = AsyncMock(spec=Track17Tracker)
    track17_mock.fetch = AsyncMock(
        return_value=TrackingResult(
            tracking_number="EE123456789CN",
            found=True,
            carrier_name="track17",
            carrier_code="track17",
            status=ShipmentStatus.IN_TRANSIT,
            events=[TrackingEvent(time="t", description="In transit", location="L")],
            last_event="In transit",
            last_event_time="t",
        )
    )

    tracker = EmsTracker(track17=track17_mock)
    result = await tracker.fetch("EE123456789CN")

    assert result.found
    assert result.carrier_name == "EMS"
    assert result.carrier_code == "ems"
    assert result.status == ShipmentStatus.IN_TRANSIT
