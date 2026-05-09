"""Tests for trackers.canada_post — Canada Post Tier S scraper."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from parcel_tracker.core.http_client import HttpClient
from parcel_tracker.db.models import ShipmentStatus
from parcel_tracker.trackers.canada_post import CanadaPostTracker


def test_detects_canada_post_pattern() -> None:
    """Canada Post detect: 16-digit domestic IDs, CA UPU IDs, and canadapost-postescanada.ca URL."""
    t = CanadaPostTracker()
    # Positive samples
    assert t.detect("1234567890123456") is True  # Canada Post domestic 16-digit
    assert t.detect("AB123456789CA") is True  # UPU CA
    assert t.detect("RR987654321CA") is True  # UPU CA (registered)
    # URL pattern
    assert (
        t.detect(
            "https://www.canadapost-postescanada.ca/track-reperage/en?trackingNumber=1234567890123456"
        )
        is True
    )
    # Negative samples
    assert t.detect("INVALID") is False
    assert t.detect("") is False
    assert t.detect("123") is False  # too short
    assert t.detect("AB123456789FR") is False  # wrong country (FR instead of CA)


def test_class_attributes() -> None:
    """Verify class metadata is correctly declared."""
    assert CanadaPostTracker.name == "canada_post"
    assert CanadaPostTracker.priority == 80
    assert "CA" in CanadaPostTracker.country_codes


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
    """Parser correctly maps Canada Post HTML fixtures to canonical TrackingResult."""
    html = (fixtures_dir / "trackers" / "canada_post" / fixture_file).read_text()

    mock_client = AsyncMock(spec=HttpClient)
    mock_client.get = AsyncMock(return_value=_make_response_mock(200, html))

    tracker = CanadaPostTracker(http_client=mock_client)
    result = await tracker.fetch("1234567890123456")

    assert result.tracking_number == "1234567890123456"
    assert result.found is True
    assert result.carrier_name == "Canada Post"
    assert result.carrier_code == "canada_post"
    assert result.status is expected_status
    assert len(result.events) >= expected_events_min
    # last_event populated from first parsed event
    assert result.last_event is not None
    assert result.last_event_time is not None
    # Tracker uses the configured TRACK_URL with trackingNumber param
    mock_client.get.assert_awaited_once()
    call_args = mock_client.get.await_args
    assert call_args.args[0] == CanadaPostTracker.TRACK_URL
    assert call_args.kwargs["params"] == {"trackingNumber": "1234567890123456"}


@pytest.mark.asyncio
async def test_fetch_handles_http_error() -> None:
    """HTTP 500 → returns found=False with error string, no crash."""
    mock_client = AsyncMock(spec=HttpClient)
    mock_client.get = AsyncMock(return_value=_make_response_mock(500, ""))

    tracker = CanadaPostTracker(http_client=mock_client)
    result = await tracker.fetch("1234567890123456")

    assert result.found is False
    assert result.error is not None
    assert "500" in result.error


@pytest.mark.asyncio
async def test_fetch_handles_not_found_fixture(fixtures_dir: Path) -> None:
    """An error/not-found page returns found=False without crashing."""
    html = (fixtures_dir / "trackers" / "canada_post" / "not_found.html").read_text()

    mock_client = AsyncMock(spec=HttpClient)
    mock_client.get = AsyncMock(return_value=_make_response_mock(200, html))

    tracker = CanadaPostTracker(http_client=mock_client)
    result = await tracker.fetch("1234567890123456")

    assert result.found is False
    assert result.tracking_number == "1234567890123456"
    assert result.carrier_name == "Canada Post"


@pytest.mark.asyncio
async def test_fetch_handles_network_exception() -> None:
    """Network error → returns found=False with error string, no crash."""
    mock_client = AsyncMock(spec=HttpClient)
    mock_client.get = AsyncMock(side_effect=RuntimeError("connection refused"))

    tracker = CanadaPostTracker(http_client=mock_client)
    result = await tracker.fetch("1234567890123456")

    assert result.found is False
    assert result.error is not None
    assert "connection refused" in result.error
