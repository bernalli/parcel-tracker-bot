"""Tests for trackers.usps — USPS Tier S scraper."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from parcel_tracker.core.http_client import HttpClient
from parcel_tracker.db.models import ShipmentStatus
from parcel_tracker.trackers.usps import UspsTracker


def test_detects_usps_pattern() -> None:
    """USPS detect: 20/22-digit numeric IDs, EE/EM/EX/EZ-prefix UPU IDs, and tools.usps.com URL."""
    t = UspsTracker()
    # Positive samples
    assert t.detect("94055118995600000000") is True  # 20-digit standard (^9\d{19}$)
    assert t.detect("EA123456789US") is True  # UPU international (^E[A-Z]\d{9}US$)
    assert t.detect("9100123456789012345678") is True  # 22-digit Priority/Express (^91\d{20}$)
    # URL pattern
    assert (
        t.detect("https://tools.usps.com/go/TrackConfirmAction?tLabels=9405511899560000000000")
        is True
    )
    # Negative samples
    assert t.detect("INVALID") is False
    assert t.detect("") is False
    assert t.detect("1Z999AA10123456784") is False  # UPS-like


def test_class_attributes() -> None:
    """Verify class metadata is correctly declared."""
    assert UspsTracker.name == "usps"
    assert UspsTracker.priority == 90
    assert "US" in UspsTracker.country_codes


def _make_response_mock(status_code: int, text: str) -> MagicMock:
    """Build a fake httpx.Response."""
    response = MagicMock()
    response.status_code = status_code
    response.text = text
    return response


@pytest.mark.parametrize(
    ("fixture_file", "expected_status", "expected_events_min"),
    [
        ("delivered.html", ShipmentStatus.DELIVERED, 5),
        ("in_transit.html", ShipmentStatus.IN_TRANSIT, 5),
        ("out_for_delivery.html", ShipmentStatus.OUT_FOR_DELIVERY, 4),
    ],
)
@pytest.mark.asyncio
async def test_fetch_parses_status_and_events(
    fixtures_dir: Path,
    fixture_file: str,
    expected_status: ShipmentStatus,
    expected_events_min: int,
) -> None:
    """Parser correctly maps USPS HTML fixtures to canonical TrackingResult."""
    html = (fixtures_dir / "trackers" / "usps" / fixture_file).read_text()

    mock_client = AsyncMock(spec=HttpClient)
    mock_client.get = AsyncMock(return_value=_make_response_mock(200, html))

    tracker = UspsTracker(http_client=mock_client)
    result = await tracker.fetch("9405511899560000000000")

    assert result.tracking_number == "9405511899560000000000"
    assert result.found is True
    assert result.carrier_name == "USPS"
    assert result.carrier_code == "usps"
    assert result.status is expected_status
    assert len(result.events) >= expected_events_min
    # last_event populated from first parsed event
    assert result.last_event is not None
    assert result.last_event_time is not None
    # Tracker uses the configured TRACK_URL with tLabels param
    mock_client.get.assert_awaited_once()
    call_args = mock_client.get.await_args
    assert call_args.args[0] == UspsTracker.TRACK_URL
    assert call_args.kwargs["params"] == {"tLabels": "9405511899560000000000"}


@pytest.mark.asyncio
async def test_fetch_handles_http_error() -> None:
    """HTTP 500 → returns found=False with error string, no crash."""
    mock_client = AsyncMock(spec=HttpClient)
    mock_client.get = AsyncMock(return_value=_make_response_mock(500, ""))

    tracker = UspsTracker(http_client=mock_client)
    result = await tracker.fetch("9405511899560000000000")

    assert result.found is False
    assert result.error is not None
    assert "500" in result.error


@pytest.mark.asyncio
async def test_fetch_handles_not_found_fixture(fixtures_dir: Path) -> None:
    """An error/not-found page returns found=False without crashing."""
    html = (fixtures_dir / "trackers" / "usps" / "not_found.html").read_text()

    mock_client = AsyncMock(spec=HttpClient)
    mock_client.get = AsyncMock(return_value=_make_response_mock(200, html))

    tracker = UspsTracker(http_client=mock_client)
    result = await tracker.fetch("9405511899560000000000")

    assert result.found is False
    assert result.tracking_number == "9405511899560000000000"
    assert result.carrier_name == "USPS"


@pytest.mark.asyncio
async def test_fetch_handles_network_exception() -> None:
    """Network error → returns found=False with error string, no crash."""
    mock_client = AsyncMock(spec=HttpClient)
    mock_client.get = AsyncMock(side_effect=RuntimeError("connection refused"))

    tracker = UspsTracker(http_client=mock_client)
    result = await tracker.fetch("9405511899560000000000")

    assert result.found is False
    assert result.error is not None
    assert "connection refused" in result.error
