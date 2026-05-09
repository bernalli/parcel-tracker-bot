"""Tests for AmazonLogisticsTracker (Tier D)."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from parcel_tracker.core.tracker_base import TrackingResult
from parcel_tracker.db.models import ShipmentStatus, TrackingEvent
from parcel_tracker.trackers.amazon_logistics import AmazonLogisticsTracker
from parcel_tracker.trackers.track17 import Track17Tracker


@pytest.mark.parametrize(
    "tracking_id,expected_match",
    [
        ("TBA1234567890", True),
        ("TBA987654321012", True),
        ("1Z999AA10123456784", False),
        ("RANDOM", False),
        ("", False),
    ],
)
def test_amazon_detection(tracking_id: str, expected_match: bool) -> None:
    tracker = AmazonLogisticsTracker()
    assert tracker.detect(tracking_id) is expected_match


async def test_amazon_returns_not_found_without_track17() -> None:
    tracker = AmazonLogisticsTracker(track17=None)
    result = await tracker.fetch("TBA1234567890")
    assert not result.found
    assert result.carrier_name == "Amazon Logistics"
    assert result.carrier_code == "amazon"


async def test_amazon_delegates_and_rebrands() -> None:
    track17_mock = AsyncMock(spec=Track17Tracker)
    track17_mock.fetch = AsyncMock(
        return_value=TrackingResult(
            tracking_number="TBA1234567890",
            found=True,
            carrier_name="track17",
            carrier_code="track17",
            status=ShipmentStatus.IN_TRANSIT,
            events=[TrackingEvent(time="t", description="In transit", location="L")],
            last_event="In transit",
            last_event_time="t",
        )
    )

    tracker = AmazonLogisticsTracker(track17=track17_mock)
    result = await tracker.fetch("TBA1234567890")

    assert result.found
    assert result.carrier_name == "Amazon Logistics"
    assert result.carrier_code == "amazon"
    assert result.status == ShipmentStatus.IN_TRANSIT
