"""Tests for core.tracker_base — abstract contract."""

from __future__ import annotations

import re

import pytest

from parcel_tracker.core.tracker_base import (
    AbstractTracker,
    TrackingResult,
)
from parcel_tracker.db.models import ShipmentStatus, TrackingEvent


class _FakeTracker(AbstractTracker):
    name = "fake"
    priority = 50
    country_codes = ["XX"]
    tracking_id_patterns = [re.compile(r"^FAKE\d{4}$")]
    url_patterns: list[re.Pattern[str]] = []

    async def fetch(self, tracking_id: str) -> TrackingResult:
        return TrackingResult(
            tracking_number=tracking_id,
            found=True,
            status=ShipmentStatus.IN_TRANSIT,
            carrier_name="Fake",
            events=[TrackingEvent(time="now", description="fake event")],
        )


def test_detect_returns_true_for_match() -> None:
    tracker = _FakeTracker()
    assert tracker.detect("FAKE1234") is True


def test_detect_returns_false_for_mismatch() -> None:
    tracker = _FakeTracker()
    assert tracker.detect("XYZ") is False


def test_abstract_cannot_be_instantiated() -> None:
    with pytest.raises(TypeError):
        AbstractTracker()  # type: ignore[abstract]


@pytest.mark.asyncio
async def test_fetch_returns_tracking_result() -> None:
    tracker = _FakeTracker()
    result = await tracker.fetch("FAKE1234")
    assert result.found is True
    assert result.status is ShipmentStatus.IN_TRANSIT
