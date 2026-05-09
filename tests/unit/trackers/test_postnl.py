"""Tests for trackers.postnl — PostNL (Netherlands) Tier S scraper."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from parcel_tracker.core.http_client import HttpClient
from parcel_tracker.db.models import ShipmentStatus
from parcel_tracker.trackers.postnl import PostnlTracker


def test_detects_postnl_pattern() -> None:
    """PostNL detect: 3S-prefix domestic, UPU NL-suffix, LL-prefix UPU, postnl.nl/track URLs."""
    t = PostnlTracker()
    # Positive samples — PostNL formats
    assert t.detect("3SABCDEFGHI01") is True  # 3S prefix + 11 chars (13 total)
    assert t.detect("3SXYZ12345AB") is True  # 3S prefix + 10 chars (12 total)
    assert t.detect("RR123456789NL") is True  # UPU NL-suffix
    assert t.detect("LL123456789NL") is True  # PostNL LL-prefix UPU variant
    # URL patterns
    assert t.detect("https://jouw.postnl.nl/track-and-trace?barcode=3SABCDEFGHI01") is True
    # Negative samples
    assert t.detect("INVALID") is False
    assert t.detect("") is False
    assert t.detect("AB123456789BE") is False  # Bpost-like, wrong country


def test_class_attributes() -> None:
    """Verify class metadata is correctly declared."""
    assert PostnlTracker.name == "postnl"
    assert PostnlTracker.priority == 60
    assert PostnlTracker.country_codes == ["NL"]


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
    """Parser correctly maps PostNL HTML fixtures to canonical TrackingResult."""
    html = (fixtures_dir / "trackers" / "postnl" / fixture_file).read_text()

    mock_client = AsyncMock(spec=HttpClient)
    mock_client.get = AsyncMock(return_value=_make_response_mock(200, html))

    tracker = PostnlTracker(http_client=mock_client)
    result = await tracker.fetch("3SABCDEFGHI01")

    assert result.tracking_number == "3SABCDEFGHI01"
    assert result.found is True
    assert result.carrier_name == "PostNL"
    assert result.carrier_code == "postnl"
    assert result.status is expected_status
    assert len(result.events) >= expected_events_min
    # last_event populated from first parsed event
    assert result.last_event is not None
    assert result.last_event_time is not None
    # Tracker uses the configured TRACK_URL with `barcode` querystring param
    mock_client.get.assert_awaited_once()
    call_args = mock_client.get.await_args
    assert call_args.args[0] == PostnlTracker.TRACK_URL
    assert call_args.kwargs["params"] == {"barcode": "3SABCDEFGHI01"}


@pytest.mark.asyncio
async def test_fetch_handles_http_error() -> None:
    """HTTP 500 → returns found=False with error string, no crash."""
    mock_client = AsyncMock(spec=HttpClient)
    mock_client.get = AsyncMock(return_value=_make_response_mock(500, ""))

    tracker = PostnlTracker(http_client=mock_client)
    result = await tracker.fetch("3SABCDEFGHI01")

    assert result.found is False
    assert result.error is not None
    assert "500" in result.error


@pytest.mark.asyncio
async def test_fetch_handles_not_found_fixture(fixtures_dir: Path) -> None:
    """An error/not-found page returns found=False without crashing."""
    html = (fixtures_dir / "trackers" / "postnl" / "not_found.html").read_text()

    mock_client = AsyncMock(spec=HttpClient)
    mock_client.get = AsyncMock(return_value=_make_response_mock(200, html))

    tracker = PostnlTracker(http_client=mock_client)
    result = await tracker.fetch("3SABCDEFGHI01")

    assert result.found is False
    assert result.tracking_number == "3SABCDEFGHI01"
    assert result.carrier_name == "PostNL"


@pytest.mark.asyncio
async def test_fetch_handles_network_exception() -> None:
    """Network error → returns found=False with error string, no crash."""
    mock_client = AsyncMock(spec=HttpClient)
    mock_client.get = AsyncMock(side_effect=RuntimeError("connection refused"))

    tracker = PostnlTracker(http_client=mock_client)
    result = await tracker.fetch("3SABCDEFGHI01")

    assert result.found is False
    assert result.error is not None
    assert "connection refused" in result.error
