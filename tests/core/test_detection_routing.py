"""Integration test: 24 sample tracking IDs route to the expected primary tracker.

This test exercises the full registry stack (built-in registration + detector
priority sort) to ensure the tracker priority ladder is internally consistent.
"""

from __future__ import annotations

from dataclasses import dataclass
from unittest.mock import MagicMock

import pytest

from parcel_tracker.config import Config
from parcel_tracker.core.detector import CourierDetector
from parcel_tracker.core.registry import TrackerRegistry
from parcel_tracker.trackers import register_builtins


@dataclass(frozen=True)
class _Sample:
    tracking_id: str
    expected_tracker_name: str


SAMPLES: list[_Sample] = [
    # Tier S — domain-specific high priority
    _Sample("1Z999AA10123456784", "ups"),
    _Sample("9405511899560000000000", "usps"),
    _Sample("AB123456789GB", "royal_mail"),
    _Sample("1A23456789012FR", "la_poste"),
    _Sample("RR123456789DE", "deutsche_post"),
    _Sample("AB123456789AU", "australia_post"),
    _Sample("1234567890123456", "canada_post"),
    _Sample("AB123456789ES", "correos"),
    _Sample("AB123456789BR", "correios"),
    # Tier S — generic numeric / URL-discriminated
    _Sample("123456789012", "fedex"),
    _Sample("123456789012345", "fedex"),
    _Sample("12345678901234", "dpd"),
    _Sample("1234567890123", "gls_europe"),
    _Sample("JD0123456789012345", "yodel"),
    _Sample("T0123456789012345", "evri"),
    _Sample("RR123456789BE", "bpost"),
    _Sample("3SABCDEFGHI012", "postnl"),
    _Sample("RR123456789AT", "oesterreichische_post"),
    _Sample("99.12.345678.12345678", "swisspost"),
    # Tier D
    _Sample("TBA1234567890", "amazon_logistics"),
    _Sample("LX123456789CN", "china_post"),
    _Sample("EE123456789JP", "ems"),
    _Sample("RR123456789SG", "singapore_post"),
    _Sample(
        "EM987654321JP", "ems"
    ),  # ambiguous EM-prefix; expect ems > japan_post (priority 33 vs 31)
    # Existing trackers (preserved by register_builtins)
    _Sample("1234567890", "dhl"),  # DHL Express 10-digit
]


@pytest.fixture
def _registry_and_detector() -> tuple[TrackerRegistry, CourierDetector]:
    config = MagicMock(spec=Config)
    config.track17_api_key = ""  # disable Track17 (still registers Tier D with track17=None)
    registry = TrackerRegistry()
    register_builtins(registry, config)
    detector = CourierDetector(registry)
    return registry, detector


@pytest.mark.parametrize("sample", SAMPLES, ids=lambda s: s.tracking_id)
def test_detection_routes_to_expected_tracker(
    sample: _Sample,
    _registry_and_detector: tuple[TrackerRegistry, CourierDetector],
) -> None:
    _registry, detector = _registry_and_detector
    matches = detector.detect(sample.tracking_id)
    assert matches, f"No tracker matches {sample.tracking_id}"
    assert matches[0].name == sample.expected_tracker_name, (
        f"For {sample.tracking_id} expected {sample.expected_tracker_name}, "
        f"got {[m.name for m in matches]}"
    )


def test_all_24_new_trackers_registered(
    _registry_and_detector: tuple[TrackerRegistry, CourierDetector],
) -> None:
    """Ensure register_builtins added all 24 built-in trackers."""
    registry, _detector = _registry_and_detector
    expected = {
        "ups",
        "usps",
        "royal_mail",
        "la_poste",
        "deutsche_post",
        "aramex",
        "australia_post",
        "canada_post",
        "correos",
        "correios",
        "fedex",
        "dpd",
        "gls_europe",
        "yodel",
        "evri",
        "bpost",
        "postnl",
        "oesterreichische_post",
        "swisspost",
        "amazon_logistics",
        "china_post",
        "ems",
        "singapore_post",
        "japan_post",
    }
    registered = {t.name for t in registry.iter_all()}
    missing = expected - registered
    assert not missing, f"Missing trackers in builtins: {missing}"
