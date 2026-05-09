"""Tests for trackers.ups — UPS Tier S scraper."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from parcel_tracker.core.http_client import HttpClient
from parcel_tracker.db.models import ShipmentStatus
from parcel_tracker.trackers.ups import UpsTracker


def test_detects_ups_pattern() -> None:
    """UPS detect: 18-char 1Z prefix patterns and ups.com URL pattern."""
    t = UpsTracker()
    # Positive samples (18 chars, 1Z prefix)
    assert t.detect("1Z999AA10123456784") is True
    assert t.detect("1ZAB1234567890123Z") is True
    # URL pattern
    assert t.detect("https://www.ups.com/track?tracknum=1Z999AA10123456784") is True
    # Negative samples
    assert t.detect("INVALID") is False
    assert t.detect("") is False
    assert t.detect("AB123456789GB") is False  # Royal Mail-like
    assert t.detect("JD014600003725123456") is False  # DHL-like


def test_class_attributes() -> None:
    """Verify class metadata is correctly declared."""
    assert UpsTracker.name == "ups"
    assert UpsTracker.priority == 90
    assert "US" in UpsTracker.country_codes
    assert "GLOBAL" in UpsTracker.country_codes


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
    """Parser correctly maps UPS HTML fixtures to canonical TrackingResult."""
    html = (fixtures_dir / "trackers" / "ups" / fixture_file).read_text()

    mock_client = AsyncMock(spec=HttpClient)
    mock_client.get = AsyncMock(return_value=_make_response_mock(200, html))

    tracker = UpsTracker(http_client=mock_client)
    result = await tracker.fetch("1Z999AA10123456784")

    assert result.tracking_number == "1Z999AA10123456784"
    assert result.found is True
    assert result.carrier_name == "UPS"
    assert result.carrier_code == "ups"
    assert result.status is expected_status
    assert len(result.events) >= expected_events_min
    # last_event populated from first parsed event
    assert result.last_event is not None
    assert result.last_event_time is not None
    # Tracker uses the configured TRACK_URL
    mock_client.get.assert_awaited_once()
    call_args = mock_client.get.await_args
    assert call_args.args[0] == UpsTracker.TRACK_URL
    assert call_args.kwargs["params"] == {"tracknum": "1Z999AA10123456784"}


@pytest.mark.asyncio
async def test_fetch_handles_http_error() -> None:
    """HTTP 500 → returns found=False with error string, no crash."""
    mock_client = AsyncMock(spec=HttpClient)
    mock_client.get = AsyncMock(return_value=_make_response_mock(500, ""))

    tracker = UpsTracker(http_client=mock_client)
    result = await tracker.fetch("1Z999AA10123456784")

    assert result.found is False
    assert result.error is not None
    assert "500" in result.error


@pytest.mark.asyncio
async def test_fetch_handles_not_found_fixture(fixtures_dir: Path) -> None:
    """An error/not-found page returns found=False without crashing."""
    html = (fixtures_dir / "trackers" / "ups" / "not_found.html").read_text()

    mock_client = AsyncMock(spec=HttpClient)
    mock_client.get = AsyncMock(return_value=_make_response_mock(200, html))

    tracker = UpsTracker(http_client=mock_client)
    result = await tracker.fetch("1Z999AA10123456784")

    assert result.found is False
    assert result.tracking_number == "1Z999AA10123456784"
    assert result.carrier_name == "UPS"


@pytest.mark.asyncio
async def test_fetch_handles_network_exception() -> None:
    """Network error → returns found=False with error string, no crash."""
    mock_client = AsyncMock(spec=HttpClient)
    mock_client.get = AsyncMock(side_effect=RuntimeError("connection refused"))

    tracker = UpsTracker(http_client=mock_client)
    result = await tracker.fetch("1Z999AA10123456784")

    assert result.found is False
    assert result.error is not None
    assert "connection refused" in result.error
