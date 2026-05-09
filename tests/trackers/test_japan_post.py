"""Tests for JapanPostTracker (Tier D)."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from parcel_tracker.core.tracker_base import TrackingResult
from parcel_tracker.db.models import ShipmentStatus, TrackingEvent
from parcel_tracker.trackers.japan_post import JapanPostTracker
from parcel_tracker.trackers.track17 import Track17Tracker


@pytest.mark.parametrize(
    "tracking_id,expected_match",
    [
        ("RR123456789JP", True),
        ("EM987654321JP", True),
        ("RR123456789CN", False),
        ("LX987654321SG", False),
        ("", False),
    ],
)
def test_japan_post_detection(tracking_id: str, expected_match: bool) -> None:
    tracker = JapanPostTracker()
    assert tracker.detect(tracking_id) is expected_match


async def test_japan_post_returns_not_found_without_track17() -> None:
    tracker = JapanPostTracker(track17=None)
    result = await tracker.fetch("RR123456789JP")
    assert not result.found
    assert result.carrier_name == "Japan Post"
    assert result.carrier_code == "jp_post"


async def test_japan_post_delegates_and_rebrands() -> None:
    track17_mock = AsyncMock(spec=Track17Tracker)
    track17_mock.fetch = AsyncMock(
        return_value=TrackingResult(
            tracking_number="RR123456789JP",
            found=True,
            carrier_name="track17",
            carrier_code="track17",
            status=ShipmentStatus.IN_TRANSIT,
            events=[TrackingEvent(time="t", description="In transit", location="L")],
            last_event="In transit",
            last_event_time="t",
        )
    )

    tracker = JapanPostTracker(track17=track17_mock)
    result = await tracker.fetch("RR123456789JP")

    assert result.found
    assert result.carrier_name == "Japan Post"
    assert result.carrier_code == "jp_post"
    assert result.status == ShipmentStatus.IN_TRANSIT
