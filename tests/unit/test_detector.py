"""Tests for core.detector — auto-detect courier."""

from __future__ import annotations

import re

from parcel_tracker.core.detector import CourierDetector
from parcel_tracker.core.registry import TrackerRegistry
from parcel_tracker.core.tracker_base import AbstractTracker, TrackingResult
from parcel_tracker.db.models import ShipmentStatus


class _DhlLike(AbstractTracker):
    name = "dhl_like"
    priority = 80
    tracking_id_patterns = [re.compile(r"^\d{10}$"), re.compile(r"^JD\d+$")]

    async def fetch(self, tracking_id: str) -> TrackingResult:
        return TrackingResult(
            tracking_number=tracking_id,
            found=True,
            status=ShipmentStatus.IN_TRANSIT,
        )


class _FedexLike(AbstractTracker):
    name = "fedex_like"
    priority = 70
    tracking_id_patterns = [re.compile(r"^\d{12}$")]

    async def fetch(self, tracking_id: str) -> TrackingResult:
        return TrackingResult(tracking_number=tracking_id, found=False)


def test_detect_returns_match_by_priority() -> None:
    registry = TrackerRegistry()
    registry.register(_DhlLike())
    registry.register(_FedexLike())

    detector = CourierDetector(registry)
    matches = detector.detect("1234567890")  # 10 digits → DHL pattern
    assert matches[0].name == "dhl_like"


def test_detect_no_match_returns_empty() -> None:
    registry = TrackerRegistry()
    registry.register(_DhlLike())

    detector = CourierDetector(registry)
    assert detector.detect("garbage") == []


def test_detect_returns_higher_priority_first() -> None:
    registry = TrackerRegistry()
    registry.register(_FedexLike())  # priority 70
    registry.register(_DhlLike())  # priority 80

    detector = CourierDetector(registry)
    matches = detector.detect("123456789012")  # 12 digits → only FedEx
    assert [t.name for t in matches] == ["fedex_like"]
