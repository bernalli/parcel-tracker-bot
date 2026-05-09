"""Tests for trackers.aramex — Aramex Tier S scraper."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from parcel_tracker.core.http_client import HttpClient
from parcel_tracker.db.models import ShipmentStatus
from parcel_tracker.trackers.aramex import AramexTracker


def test_detects_aramex_pattern() -> None:
    """Aramex detect: 10-12 digit numeric IDs and aramex.com/track URL."""
    t = AramexTracker()
    # Positive samples (10, 11, 12 digit numeric)
    assert t.detect("1234567890") is True
    assert t.detect("12345678901") is True
    assert t.detect("123456789012") is True
    # URL pattern
    assert t.detect("https://www.aramex.com/track/results?ShipmentNumber=1234567890") is True
    # Negative samples
    assert t.detect("INVALID") is False
    assert t.detect("") is False
    assert t.detect("123") is False  # too short
    assert t.detect("1234567890123") is False  # too long (13 digits)


def test_class_attributes() -> None:
    """Verify class metadata is correctly declared."""
    assert AramexTracker.name == "aramex"
    assert AramexTracker.priority == 80
    assert "AE" in AramexTracker.country_codes
    assert "GLOBAL" in AramexTracker.country_codes


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
    """Parser correctly maps Aramex HTML fixtures to canonical TrackingResult."""
    html = (fixtures_dir / "trackers" / "aramex" / fixture_file).read_text()

    mock_client = AsyncMock(spec=HttpClient)
    mock_client.get = AsyncMock(return_value=_make_response_mock(200, html))

    tracker = AramexTracker(http_client=mock_client)
    result = await tracker.fetch("1234567890")

    assert result.tracking_number == "1234567890"
    assert result.found is True
    assert result.carrier_name == "Aramex"
    assert result.carrier_code == "aramex"
    assert result.status is expected_status
    assert len(result.events) >= expected_events_min
    # last_event populated from first parsed event
    assert result.last_event is not None
    assert result.last_event_time is not None
    # Tracker uses the configured TRACK_URL with ShipmentNumber param
    mock_client.get.assert_awaited_once()
    call_args = mock_client.get.await_args
    assert call_args.args[0] == AramexTracker.TRACK_URL
    assert call_args.kwargs["params"] == {"ShipmentNumber": "1234567890"}


@pytest.mark.asyncio
async def test_fetch_handles_http_error() -> None:
    """HTTP 500 → returns found=False with error string, no crash."""
    mock_client = AsyncMock(spec=HttpClient)
    mock_client.get = AsyncMock(return_value=_make_response_mock(500, ""))

    tracker = AramexTracker(http_client=mock_client)
    result = await tracker.fetch("1234567890")

    assert result.found is False
    assert result.error is not None
    assert "500" in result.error


@pytest.mark.asyncio
async def test_fetch_handles_not_found_fixture(fixtures_dir: Path) -> None:
    """An error/not-found page returns found=False without crashing."""
    html = (fixtures_dir / "trackers" / "aramex" / "not_found.html").read_text()

    mock_client = AsyncMock(spec=HttpClient)
    mock_client.get = AsyncMock(return_value=_make_response_mock(200, html))

    tracker = AramexTracker(http_client=mock_client)
    result = await tracker.fetch("1234567890")

    assert result.found is False
    assert result.tracking_number == "1234567890"
    assert result.carrier_name == "Aramex"


@pytest.mark.asyncio
async def test_fetch_handles_network_exception() -> None:
    """Network error → returns found=False with error string, no crash."""
    mock_client = AsyncMock(spec=HttpClient)
    mock_client.get = AsyncMock(side_effect=RuntimeError("connection refused"))

    tracker = AramexTracker(http_client=mock_client)
    result = await tracker.fetch("1234567890")

    assert result.found is False
    assert result.error is not None
    assert "connection refused" in result.error
