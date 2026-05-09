"""Tests for trackers.swisspost — Swiss Post (Switzerland) Tier S scraper."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from parcel_tracker.core.http_client import HttpClient
from parcel_tracker.db.models import ShipmentStatus
from parcel_tracker.trackers.swisspost import SwissPostTracker


def test_detects_swisspost_pattern() -> None:
    """Detect: UPU CH-suffix, Swiss Post 99.xx.xxxxxx.xxxxxxxx and 99-prefix 18-digit, service.post.ch URLs."""
    t = SwissPostTracker()
    # Positive samples
    assert t.detect("RR123456789CH") is True  # UPU CH-suffix
    assert t.detect("99.12.345678.12345678") is True  # Swiss Post barcode dotted format
    assert t.detect("991234567890123456") is True  # Swiss Post 18-digit alternate
    # URL patterns
    assert (
        t.detect("https://service.post.ch/EasyTrack/?formattedParcelCodes=99.12.345678.12345678")
        is True
    )
    # Negative samples
    assert t.detect("INVALID") is False
    assert t.detect("") is False
    assert t.detect("AB123456789AT") is False  # Austrian Post-like, wrong country


def test_class_attributes() -> None:
    """Verify class metadata is correctly declared."""
    assert SwissPostTracker.name == "swisspost"
    assert SwissPostTracker.priority == 60
    assert SwissPostTracker.country_codes == ["CH"]


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
    """Parser correctly maps Swiss Post HTML fixtures to canonical TrackingResult."""
    html = (fixtures_dir / "trackers" / "swisspost" / fixture_file).read_text()

    mock_client = AsyncMock(spec=HttpClient)
    mock_client.get = AsyncMock(return_value=_make_response_mock(200, html))

    tracker = SwissPostTracker(http_client=mock_client)
    result = await tracker.fetch("RR123456789CH")

    assert result.tracking_number == "RR123456789CH"
    assert result.found is True
    assert result.carrier_name == "Swiss Post"
    assert result.carrier_code == "swisspost"
    assert result.status is expected_status
    assert len(result.events) >= expected_events_min
    # last_event populated from first parsed event
    assert result.last_event is not None
    assert result.last_event_time is not None
    # Tracker uses the configured TRACK_URL with `formattedParcelCodes` querystring param
    mock_client.get.assert_awaited_once()
    call_args = mock_client.get.await_args
    assert call_args.args[0] == SwissPostTracker.TRACK_URL
    assert call_args.kwargs["params"] == {"formattedParcelCodes": "RR123456789CH"}


@pytest.mark.asyncio
async def test_fetch_handles_http_error() -> None:
    """HTTP 500 → returns found=False with error string, no crash."""
    mock_client = AsyncMock(spec=HttpClient)
    mock_client.get = AsyncMock(return_value=_make_response_mock(500, ""))

    tracker = SwissPostTracker(http_client=mock_client)
    result = await tracker.fetch("RR123456789CH")

    assert result.found is False
    assert result.error is not None
    assert "500" in result.error


@pytest.mark.asyncio
async def test_fetch_handles_not_found_fixture(fixtures_dir: Path) -> None:
    """An error/not-found page returns found=False without crashing."""
    html = (fixtures_dir / "trackers" / "swisspost" / "not_found.html").read_text()

    mock_client = AsyncMock(spec=HttpClient)
    mock_client.get = AsyncMock(return_value=_make_response_mock(200, html))

    tracker = SwissPostTracker(http_client=mock_client)
    result = await tracker.fetch("RR123456789CH")

    assert result.found is False
    assert result.tracking_number == "RR123456789CH"
    assert result.carrier_name == "Swiss Post"


@pytest.mark.asyncio
async def test_fetch_handles_network_exception() -> None:
    """Network error → returns found=False with error string, no crash."""
    mock_client = AsyncMock(spec=HttpClient)
    mock_client.get = AsyncMock(side_effect=RuntimeError("connection refused"))

    tracker = SwissPostTracker(http_client=mock_client)
    result = await tracker.fetch("RR123456789CH")

    assert result.found is False
    assert result.error is not None
    assert "connection refused" in result.error
