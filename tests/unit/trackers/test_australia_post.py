"""Tests for trackers.australia_post — Australia Post Tier S scraper."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from parcel_tracker.core.http_client import HttpClient
from parcel_tracker.db.models import ShipmentStatus
from parcel_tracker.trackers.australia_post import AustraliaPostTracker


def test_detects_australia_post_pattern() -> None:
    """Australia Post detect: AU UPU IDs, AusPost barcodes, numeric variants, and auspost.com.au URL."""
    t = AustraliaPostTracker()
    # Positive samples
    assert t.detect("AB123456789AU") is True  # UPU AU
    assert t.detect("33ABCDEFGH12345678") is True  # AusPost barcode (33 + 8 letters + digits)
    assert t.detect("7ABCD12345678901") is True  # AusPost numeric variant (7 + 11-15 alnum)
    # URL pattern
    assert t.detect("https://auspost.com.au/mypost/track/details?id=AB123456789AU") is True
    # Negative samples
    assert t.detect("INVALID") is False
    assert t.detect("") is False
    assert t.detect("AB123456789NZ") is False  # wrong country (NZ instead of AU)


def test_class_attributes() -> None:
    """Verify class metadata is correctly declared."""
    assert AustraliaPostTracker.name == "australia_post"
    assert AustraliaPostTracker.priority == 80
    assert "AU" in AustraliaPostTracker.country_codes


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
    """Parser correctly maps Australia Post HTML fixtures to canonical TrackingResult."""
    html = (fixtures_dir / "trackers" / "australia_post" / fixture_file).read_text()

    mock_client = AsyncMock(spec=HttpClient)
    mock_client.get = AsyncMock(return_value=_make_response_mock(200, html))

    tracker = AustraliaPostTracker(http_client=mock_client)
    result = await tracker.fetch("AB123456789AU")

    assert result.tracking_number == "AB123456789AU"
    assert result.found is True
    assert result.carrier_name == "Australia Post"
    assert result.carrier_code == "australia_post"
    assert result.status is expected_status
    assert len(result.events) >= expected_events_min
    # last_event populated from first parsed event
    assert result.last_event is not None
    assert result.last_event_time is not None
    # Tracker uses the configured TRACK_URL with id param
    mock_client.get.assert_awaited_once()
    call_args = mock_client.get.await_args
    assert call_args.args[0] == AustraliaPostTracker.TRACK_URL
    assert call_args.kwargs["params"] == {"id": "AB123456789AU"}


@pytest.mark.asyncio
async def test_fetch_handles_http_error() -> None:
    """HTTP 500 → returns found=False with error string, no crash."""
    mock_client = AsyncMock(spec=HttpClient)
    mock_client.get = AsyncMock(return_value=_make_response_mock(500, ""))

    tracker = AustraliaPostTracker(http_client=mock_client)
    result = await tracker.fetch("AB123456789AU")

    assert result.found is False
    assert result.error is not None
    assert "500" in result.error


@pytest.mark.asyncio
async def test_fetch_handles_not_found_fixture(fixtures_dir: Path) -> None:
    """An error/not-found page returns found=False without crashing."""
    html = (fixtures_dir / "trackers" / "australia_post" / "not_found.html").read_text()

    mock_client = AsyncMock(spec=HttpClient)
    mock_client.get = AsyncMock(return_value=_make_response_mock(200, html))

    tracker = AustraliaPostTracker(http_client=mock_client)
    result = await tracker.fetch("AB123456789AU")

    assert result.found is False
    assert result.tracking_number == "AB123456789AU"
    assert result.carrier_name == "Australia Post"


@pytest.mark.asyncio
async def test_fetch_handles_network_exception() -> None:
    """Network error → returns found=False with error string, no crash."""
    mock_client = AsyncMock(spec=HttpClient)
    mock_client.get = AsyncMock(side_effect=RuntimeError("connection refused"))

    tracker = AustraliaPostTracker(http_client=mock_client)
    result = await tracker.fetch("AB123456789AU")

    assert result.found is False
    assert result.error is not None
    assert "connection refused" in result.error
