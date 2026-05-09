"""Tests for ChinaPostTracker (Tier D)."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from parcel_tracker.core.tracker_base import TrackingResult
from parcel_tracker.db.models import ShipmentStatus, TrackingEvent
from parcel_tracker.trackers.china_post import ChinaPostTracker
from parcel_tracker.trackers.track17 import Track17Tracker


@pytest.mark.parametrize(
    "tracking_id,expected_match",
    [
        ("LX123456789CN", True),
        ("RR123456789CN", True),
        ("CP123456789CN", True),
        ("AB123456789CN", False),
        ("EM987654321US", False),
        ("", False),
    ],
)
def test_china_post_detection(tracking_id: str, expected_match: bool) -> None:
    tracker = ChinaPostTracker()
    assert tracker.detect(tracking_id) is expected_match


async def test_china_post_returns_not_found_without_track17() -> None:
    tracker = ChinaPostTracker(track17=None)
    result = await tracker.fetch("LX123456789CN")
    assert not result.found
    assert result.carrier_name == "China Post"
    assert result.carrier_code == "china_post"


async def test_china_post_delegates_and_rebrands() -> None:
    track17_mock = AsyncMock(spec=Track17Tracker)
    track17_mock.fetch = AsyncMock(
        return_value=TrackingResult(
            tracking_number="LX123456789CN",
            found=True,
            carrier_name="track17",
            carrier_code="track17",
            status=ShipmentStatus.IN_TRANSIT,
            events=[TrackingEvent(time="t", description="In transit", location="L")],
            last_event="In transit",
            last_event_time="t",
        )
    )

    tracker = ChinaPostTracker(track17=track17_mock)
    result = await tracker.fetch("LX123456789CN")

    assert result.found
    assert result.carrier_name == "China Post"
    assert result.carrier_code == "china_post"
    assert result.status == ShipmentStatus.IN_TRANSIT
