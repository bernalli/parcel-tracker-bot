"""Tests for trackers.dpd — DPD Tier S scraper."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from parcel_tracker.core.http_client import HttpClient
from parcel_tracker.db.models import ShipmentStatus
from parcel_tracker.trackers.dpd import DpdTracker


def test_detects_dpd_pattern() -> None:
    """DPD detect: 14- and 17-digit numeric IDs, dpd.{de,com,co.uk} URLs with 'tracking'."""
    t = DpdTracker()
    # Positive samples — DPD numeric formats
    assert t.detect("12345678901234") is True  # 14-digit DPD
    assert t.detect("12345678901234567") is True  # 17-digit DPD
    # URL patterns
    assert t.detect("https://www.dpd.com/tracking?parcel=12345678901234") is True
    assert t.detect("https://www.dpd.co.uk/apps/tracking/?parcel=12345678901234") is True
    assert t.detect("https://www.dpd.de/sendungsverfolgung/tracking/?parcel=12345") is True
    # Negative samples
    assert t.detect("INVALID") is False
    assert t.detect("") is False
    assert t.detect("123") is False  # too short
    assert t.detect("12345678901234567890") is False  # 20 digit, too long


def test_class_attributes() -> None:
    """Verify class metadata is correctly declared."""
    assert DpdTracker.name == "dpd"
    assert DpdTracker.priority == 70
    assert "DE" in DpdTracker.country_codes
    assert "GB" in DpdTracker.country_codes
    assert "FR" in DpdTracker.country_codes
    assert "GLOBAL" in DpdTracker.country_codes


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
    """Parser correctly maps DPD HTML fixtures to canonical TrackingResult."""
    html = (fixtures_dir / "trackers" / "dpd" / fixture_file).read_text()

    mock_client = AsyncMock(spec=HttpClient)
    mock_client.get = AsyncMock(return_value=_make_response_mock(200, html))

    tracker = DpdTracker(http_client=mock_client)
    result = await tracker.fetch("12345678901234")

    assert result.tracking_number == "12345678901234"
    assert result.found is True
    assert result.carrier_name == "DPD"
    assert result.carrier_code == "dpd"
    assert result.status is expected_status
    assert len(result.events) >= expected_events_min
    # last_event populated from first parsed event
    assert result.last_event is not None
    assert result.last_event_time is not None
    # Tracker uses the configured TRACK_URL with `query` param
    mock_client.get.assert_awaited_once()
    call_args = mock_client.get.await_args
    assert call_args.args[0] == DpdTracker.TRACK_URL
    assert call_args.kwargs["params"] == {"query": "12345678901234"}


@pytest.mark.asyncio
async def test_fetch_handles_http_error() -> None:
    """HTTP 500 → returns found=False with error string, no crash."""
    mock_client = AsyncMock(spec=HttpClient)
    mock_client.get = AsyncMock(return_value=_make_response_mock(500, ""))

    tracker = DpdTracker(http_client=mock_client)
    result = await tracker.fetch("12345678901234")

    assert result.found is False
    assert result.error is not None
    assert "500" in result.error


@pytest.mark.asyncio
async def test_fetch_handles_not_found_fixture(fixtures_dir: Path) -> None:
    """An error/not-found page returns found=False without crashing."""
    html = (fixtures_dir / "trackers" / "dpd" / "not_found.html").read_text()

    mock_client = AsyncMock(spec=HttpClient)
    mock_client.get = AsyncMock(return_value=_make_response_mock(200, html))

    tracker = DpdTracker(http_client=mock_client)
    result = await tracker.fetch("12345678901234")

    assert result.found is False
    assert result.tracking_number == "12345678901234"
    assert result.carrier_name == "DPD"


@pytest.mark.asyncio
async def test_fetch_handles_network_exception() -> None:
    """Network error → returns found=False with error string, no crash."""
    mock_client = AsyncMock(spec=HttpClient)
    mock_client.get = AsyncMock(side_effect=RuntimeError("connection refused"))

    tracker = DpdTracker(http_client=mock_client)
    result = await tracker.fetch("12345678901234")

    assert result.found is False
    assert result.error is not None
    assert "connection refused" in result.error
