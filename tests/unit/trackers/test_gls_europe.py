"""Tests for trackers.gls_europe — GLS Europe Tier S scraper."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from parcel_tracker.core.http_client import HttpClient
from parcel_tracker.db.models import ShipmentStatus
from parcel_tracker.trackers.gls_europe import GlsEuropeTracker


def test_detects_gls_europe_pattern() -> None:
    """GLS detect: 11/12/14-digit numeric IDs, gls-group.eu URLs with 'tracking'."""
    t = GlsEuropeTracker()
    # Positive samples — GLS numeric formats
    assert t.detect("12345678901") is True  # 11-digit GLS
    assert t.detect("123456789012") is True  # 12-digit GLS
    assert t.detect("12345678901234") is True  # 14-digit GLS international
    # URL patterns
    assert t.detect("https://gls-group.eu/EU/en/parcel-tracking?match=12345678901") is True
    assert t.detect("https://www.gls-group.eu/DE/en/parcel-tracking") is True
    # Negative samples
    assert t.detect("INVALID") is False
    assert t.detect("") is False
    assert t.detect("123") is False  # too short


def test_class_attributes() -> None:
    """Verify class metadata is correctly declared."""
    assert GlsEuropeTracker.name == "gls_europe"
    assert GlsEuropeTracker.priority == 70
    assert "DE" in GlsEuropeTracker.country_codes
    assert "AT" in GlsEuropeTracker.country_codes
    assert "BE" in GlsEuropeTracker.country_codes
    assert "NL" in GlsEuropeTracker.country_codes
    assert "GLOBAL" in GlsEuropeTracker.country_codes


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
    """Parser correctly maps GLS Europe HTML fixtures to canonical TrackingResult."""
    html = (fixtures_dir / "trackers" / "gls_europe" / fixture_file).read_text()

    mock_client = AsyncMock(spec=HttpClient)
    mock_client.get = AsyncMock(return_value=_make_response_mock(200, html))

    tracker = GlsEuropeTracker(http_client=mock_client)
    result = await tracker.fetch("12345678901234")

    assert result.tracking_number == "12345678901234"
    assert result.found is True
    assert result.carrier_name == "GLS Europe"
    assert result.carrier_code == "gls_europe"
    assert result.status is expected_status
    assert len(result.events) >= expected_events_min
    # last_event populated from first parsed event
    assert result.last_event is not None
    assert result.last_event_time is not None
    # Tracker uses the configured TRACK_URL with `match` param
    mock_client.get.assert_awaited_once()
    call_args = mock_client.get.await_args
    assert call_args.args[0] == GlsEuropeTracker.TRACK_URL
    assert call_args.kwargs["params"] == {"match": "12345678901234"}


@pytest.mark.asyncio
async def test_fetch_handles_http_error() -> None:
    """HTTP 500 → returns found=False with error string, no crash."""
    mock_client = AsyncMock(spec=HttpClient)
    mock_client.get = AsyncMock(return_value=_make_response_mock(500, ""))

    tracker = GlsEuropeTracker(http_client=mock_client)
    result = await tracker.fetch("12345678901234")

    assert result.found is False
    assert result.error is not None
    assert "500" in result.error


@pytest.mark.asyncio
async def test_fetch_handles_not_found_fixture(fixtures_dir: Path) -> None:
    """An error/not-found page returns found=False without crashing."""
    html = (fixtures_dir / "trackers" / "gls_europe" / "not_found.html").read_text()

    mock_client = AsyncMock(spec=HttpClient)
    mock_client.get = AsyncMock(return_value=_make_response_mock(200, html))

    tracker = GlsEuropeTracker(http_client=mock_client)
    result = await tracker.fetch("12345678901234")

    assert result.found is False
    assert result.tracking_number == "12345678901234"
    assert result.carrier_name == "GLS Europe"


@pytest.mark.asyncio
async def test_fetch_handles_network_exception() -> None:
    """Network error → returns found=False with error string, no crash."""
    mock_client = AsyncMock(spec=HttpClient)
    mock_client.get = AsyncMock(side_effect=RuntimeError("connection refused"))

    tracker = GlsEuropeTracker(http_client=mock_client)
    result = await tracker.fetch("12345678901234")

    assert result.found is False
    assert result.error is not None
    assert "connection refused" in result.error
