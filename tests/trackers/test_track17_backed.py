"""Tests for Track17BackedTracker base class."""

from __future__ import annotations

import re
from typing import ClassVar
from unittest.mock import AsyncMock

from parcel_tracker.db.models import ShipmentStatus
from parcel_tracker.trackers._track17_backed import Track17BackedTracker
from parcel_tracker.trackers.track17 import Track17Tracker


class _DummyTracker(Track17BackedTracker):
    name: ClassVar[str] = "dummy"
    priority: ClassVar[int] = 50
    country_codes: ClassVar[list[str]] = ["XX"]
    tracking_id_patterns: ClassVar[list[re.Pattern[str]]] = [re.compile(r"^TEST.+$")]
    url_patterns: ClassVar[list[re.Pattern[str]]] = []
    CARRIER_NAME: ClassVar[str] = "Dummy Carrier"
    CARRIER_CODE: ClassVar[str] = "dummy"


async def test_returns_not_found_when_track17_not_configured() -> None:
    tracker = _DummyTracker(track17=None)
    result = await tracker.fetch("TEST12345")
    assert not result.found
    assert result.carrier_name == "Dummy Carrier"
    assert result.carrier_code == "dummy"
    assert result.error == "track17 not configured"


async def test_delegates_to_track17_and_rebrands() -> None:
    from parcel_tracker.core.tracker_base import TrackingResult
    from parcel_tracker.db.models import TrackingEvent

    track17_mock = AsyncMock(spec=Track17Tracker)
    track17_mock.fetch = AsyncMock(
        return_value=TrackingResult(
            tracking_number="TEST12345",
            found=True,
            carrier_name="track17",  # original (will be overridden)
            carrier_code="track17",  # original (will be overridden)
            status=ShipmentStatus.DELIVERED,
            events=[TrackingEvent(time="t", description="Delivered", location="X")],
            last_event="Delivered",
            last_event_time="t",
        )
    )

    tracker = _DummyTracker(track17=track17_mock)
    result = await tracker.fetch("test12345")  # lowercase; expect uppercase normalize call

    assert result.found
    assert result.carrier_name == "Dummy Carrier"  # rebranded
    assert result.carrier_code == "dummy"  # rebranded
    assert result.status == ShipmentStatus.DELIVERED
    track17_mock.fetch.assert_called_once_with("TEST12345")


def test_detect_matches_pattern() -> None:
    tracker = _DummyTracker()
    assert tracker.detect("TEST12345") is True
    assert tracker.detect("OTHER12345") is False
