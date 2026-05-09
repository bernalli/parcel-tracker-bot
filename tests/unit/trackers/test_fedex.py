"""Tests for trackers.fedex — FedEx Tier S scraper (with TNT legacy folded)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from parcel_tracker.core.http_client import HttpClient
from parcel_tracker.db.models import ShipmentStatus
from parcel_tracker.trackers.fedex import FedexTracker


def test_detects_fedex_pattern() -> None:
    """FedEx detect: numeric IDs, TNT legacy IDs, and fedex.com / tnt.com URLs."""
    t = FedexTracker()
    # Positive samples — FedEx numeric formats
    assert t.detect("123456789012") is True  # 12-digit FedEx Express
    assert t.detect("123456789012345") is True  # 15-digit FedEx Ground
    assert t.detect("12345678901234567890") is True  # 20-digit FedEx SmartPost
    assert t.detect("1234567890123456789012") is True  # 22-digit alternate
    # Positive samples — TNT legacy folded
    assert t.detect("GD123456789") is True  # TNT legacy GD prefix
    assert t.detect("AB123456789TN") is True  # TNT UPU legacy TN suffix
    # URL patterns
    assert t.detect("https://www.fedex.com/fedextrack/?trknbr=123456789012") is True
    assert t.detect("https://www.tnt.com/express/en_gb/site/tracking.html") is True
    # Negative samples
    assert t.detect("INVALID") is False
    assert t.detect("") is False
    assert t.detect("AB123456789FR") is False  # wrong UPU country suffix


def test_class_attributes() -> None:
    """Verify class metadata is correctly declared."""
    assert FedexTracker.name == "fedex"
    assert FedexTracker.priority == 70
    assert "US" in FedexTracker.country_codes
    assert "GLOBAL" in FedexTracker.country_codes


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
    """Parser correctly maps FedEx HTML fixtures to canonical TrackingResult."""
    html = (fixtures_dir / "trackers" / "fedex" / fixture_file).read_text()

    mock_client = AsyncMock(spec=HttpClient)
    mock_client.get = AsyncMock(return_value=_make_response_mock(200, html))

    tracker = FedexTracker(http_client=mock_client)
    result = await tracker.fetch("123456789012")

    assert result.tracking_number == "123456789012"
    assert result.found is True
    assert result.carrier_name == "FedEx"
    assert result.carrier_code == "fedex"
    assert result.status is expected_status
    assert len(result.events) >= expected_events_min
    # last_event populated from first parsed event
    assert result.last_event is not None
    assert result.last_event_time is not None
    # Tracker uses the configured TRACK_URL with `trknbr` param
    mock_client.get.assert_awaited_once()
    call_args = mock_client.get.await_args
    assert call_args.args[0] == FedexTracker.TRACK_URL
    assert call_args.kwargs["params"] == {"trknbr": "123456789012"}


@pytest.mark.asyncio
async def test_fetch_tnt_legacy_id_reports_fedex(fixtures_dir: Path) -> None:
    """TNT legacy IDs (GD prefix) flow through tracker but report carrier_name 'FedEx'."""
    html = (fixtures_dir / "trackers" / "fedex" / "tnt_legacy.html").read_text()

    mock_client = AsyncMock(spec=HttpClient)
    mock_client.get = AsyncMock(return_value=_make_response_mock(200, html))

    tracker = FedexTracker(http_client=mock_client)
    result = await tracker.fetch("GD123456789")

    assert result.tracking_number == "GD123456789"
    assert result.found is True
    # Display name remains FedEx even for TNT-pattern IDs (TNT folded into FedEx)
    assert result.carrier_name == "FedEx"
    assert result.carrier_code == "fedex"
    assert result.status is ShipmentStatus.IN_TRANSIT
    assert len(result.events) >= 4


@pytest.mark.asyncio
async def test_fetch_handles_http_error() -> None:
    """HTTP 500 → returns found=False with error string, no crash."""
    mock_client = AsyncMock(spec=HttpClient)
    mock_client.get = AsyncMock(return_value=_make_response_mock(500, ""))

    tracker = FedexTracker(http_client=mock_client)
    result = await tracker.fetch("123456789012")

    assert result.found is False
    assert result.error is not None
    assert "500" in result.error


@pytest.mark.asyncio
async def test_fetch_handles_not_found_fixture(fixtures_dir: Path) -> None:
    """An error/not-found page returns found=False without crashing."""
    html = (fixtures_dir / "trackers" / "fedex" / "not_found.html").read_text()

    mock_client = AsyncMock(spec=HttpClient)
    mock_client.get = AsyncMock(return_value=_make_response_mock(200, html))

    tracker = FedexTracker(http_client=mock_client)
    result = await tracker.fetch("123456789012")

    assert result.found is False
    assert result.tracking_number == "123456789012"
    assert result.carrier_name == "FedEx"


@pytest.mark.asyncio
async def test_fetch_handles_network_exception() -> None:
    """Network error → returns found=False with error string, no crash."""
    mock_client = AsyncMock(spec=HttpClient)
    mock_client.get = AsyncMock(side_effect=RuntimeError("connection refused"))

    tracker = FedexTracker(http_client=mock_client)
    result = await tracker.fetch("123456789012")

    assert result.found is False
    assert result.error is not None
    assert "connection refused" in result.error
