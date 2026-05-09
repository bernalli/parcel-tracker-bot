"""Tests for SingaporePostTracker (Tier D)."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from parcel_tracker.core.tracker_base import TrackingResult
from parcel_tracker.db.models import ShipmentStatus, TrackingEvent
from parcel_tracker.trackers.singapore_post import SingaporePostTracker
from parcel_tracker.trackers.track17 import Track17Tracker


@pytest.mark.parametrize(
    "tracking_id,expected_match",
    [
        ("RR123456789SG", True),
        ("LX987654321SG", True),
        ("RR123456789DE", False),
        ("AB987654321JP", False),
        ("", False),
    ],
)
def test_singapore_post_detection(tracking_id: str, expected_match: bool) -> None:
    tracker = SingaporePostTracker()
    assert tracker.detect(tracking_id) is expected_match


async def test_singapore_post_returns_not_found_without_track17() -> None:
    tracker = SingaporePostTracker(track17=None)
    result = await tracker.fetch("RR123456789SG")
    assert not result.found
    assert result.carrier_name == "Singapore Post"
    assert result.carrier_code == "sg_post"


async def test_singapore_post_delegates_and_rebrands() -> None:
    track17_mock = AsyncMock(spec=Track17Tracker)
    track17_mock.fetch = AsyncMock(
        return_value=TrackingResult(
            tracking_number="RR123456789SG",
            found=True,
            carrier_name="track17",
            carrier_code="track17",
            status=ShipmentStatus.IN_TRANSIT,
            events=[TrackingEvent(time="t", description="In transit", location="L")],
            last_event="In transit",
            last_event_time="t",
        )
    )

    tracker = SingaporePostTracker(track17=track17_mock)
    result = await tracker.fetch("RR123456789SG")

    assert result.found
    assert result.carrier_name == "Singapore Post"
    assert result.carrier_code == "sg_post"
    assert result.status == ShipmentStatus.IN_TRANSIT
