"""Tests for trackers.bpost — Bpost (Belgium) Tier S scraper."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from parcel_tracker.core.http_client import HttpClient
from parcel_tracker.db.models import ShipmentStatus
from parcel_tracker.trackers.bpost import BpostTracker


def test_detects_bpost_pattern() -> None:
    """Bpost detect: UPU [A-Z]{2}\\d{9}BE, domestic 18-digit (32 prefix), bpost.cloud URLs."""
    t = BpostTracker()
    # Positive samples — Bpost formats
    assert t.detect("AB123456789BE") is True  # UPU BE-suffix
    assert t.detect("RR987654321BE") is True  # UPU registered BE-suffix
    assert t.detect("321234567890123456") is True  # 18-digit Bpost domestic (32 prefix)
    # URL patterns
    assert t.detect("https://track.bpost.cloud/btr/web/?itemCode=AB123456789BE") is True
    # Negative samples
    assert t.detect("INVALID") is False
    assert t.detect("") is False
    assert t.detect("AB123456789NL") is False  # PostNL-like, wrong country


def test_class_attributes() -> None:
    """Verify class metadata is correctly declared."""
    assert BpostTracker.name == "bpost"
    assert BpostTracker.priority == 60
    assert BpostTracker.country_codes == ["BE"]


def _make_response_mock(status_code: int, text: str) -> MagicMock:
    """Build a fake httpx.Response."""
    response = MagicMock()
    response.status_code = status_code
    response.text = text
    return response


@pytest.mark.parametrize(
    ("fixture_file", "expected_status", "expected_events_min"),
    [
        ("delivered.html", ShipmentStatus.DELIVERED, 4),
        ("in_transit.html", ShipmentStatus.IN_TRANSIT, 4),
        ("out_for_delivery.html", ShipmentStatus.OUT_FOR_DELIVERY, 3),
    ],
)
@pytest.mark.asyncio
async def test_fetch_parses_status_and_events(
    fixtures_dir: Path,
    fixture_file: str,
    expected_status: ShipmentStatus,
    expected_events_min: int,
) -> None:
    """Parser correctly maps Bpost HTML fixtures to canonical TrackingResult."""
    html = (fixtures_dir / "trackers" / "bpost" / fixture_file).read_text()

    mock_client = AsyncMock(spec=HttpClient)
    mock_client.get = AsyncMock(return_value=_make_response_mock(200, html))

    tracker = BpostTracker(http_client=mock_client)
    result = await tracker.fetch("AB123456789BE")

    assert result.tracking_number == "AB123456789BE"
    assert result.found is True
    assert result.carrier_name == "Bpost"
    assert result.carrier_code == "bpost"
    assert result.status is expected_status
    assert len(result.events) >= expected_events_min
    # last_event populated from first parsed event
    assert result.last_event is not None
    assert result.last_event_time is not None
    # Tracker uses the configured TRACK_URL with `itemCode` querystring param
    mock_client.get.assert_awaited_once()
    call_args = mock_client.get.await_args
    assert call_args.args[0] == BpostTracker.TRACK_URL
    assert call_args.kwargs["params"] == {"itemCode": "AB123456789BE"}


@pytest.mark.asyncio
async def test_fetch_handles_http_error() -> None:
    """HTTP 500 → returns found=False with error string, no crash."""
    mock_client = AsyncMock(spec=HttpClient)
    mock_client.get = AsyncMock(return_value=_make_response_mock(500, ""))

    tracker = BpostTracker(http_client=mock_client)
    result = await tracker.fetch("AB123456789BE")

    assert result.found is False
    assert result.error is not None
    assert "500" in result.error


@pytest.mark.asyncio
async def test_fetch_handles_not_found_fixture(fixtures_dir: Path) -> None:
    """An error/not-found page returns found=False without crashing."""
    html = (fixtures_dir / "trackers" / "bpost" / "not_found.html").read_text()

    mock_client = AsyncMock(spec=HttpClient)
    mock_client.get = AsyncMock(return_value=_make_response_mock(200, html))

    tracker = BpostTracker(http_client=mock_client)
    result = await tracker.fetch("AB123456789BE")

    assert result.found is False
    assert result.tracking_number == "AB123456789BE"
    assert result.carrier_name == "Bpost"


@pytest.mark.asyncio
async def test_fetch_handles_network_exception() -> None:
    """Network error → returns found=False with error string, no crash."""
    mock_client = AsyncMock(spec=HttpClient)
    mock_client.get = AsyncMock(side_effect=RuntimeError("connection refused"))

    tracker = BpostTracker(http_client=mock_client)
    result = await tracker.fetch("AB123456789BE")

    assert result.found is False
    assert result.error is not None
    assert "connection refused" in result.error
