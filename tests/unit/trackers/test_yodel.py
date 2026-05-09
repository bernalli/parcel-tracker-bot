"""Tests for trackers.yodel — Yodel Tier S scraper."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from parcel_tracker.core.http_client import HttpClient
from parcel_tracker.db.models import ShipmentStatus
from parcel_tracker.trackers.yodel import YodelTracker


def test_detects_yodel_pattern() -> None:
    """Yodel detect: JD\\d{16} (18 chars) and Y\\d{14} (15 chars), yodel.co.uk URLs.

    Note: DHL eCommerce uses JD\\d{18} (20 chars) — distinct length, must NOT be claimed by Yodel.
    """
    t = YodelTracker()
    # Positive samples — Yodel formats
    assert t.detect("JD0123456789012345") is True  # 18 chars, JD + 16 digits
    assert t.detect("Y12345678901234") is True  # 15 chars, Y + 14 digits
    # URL patterns
    assert t.detect("https://www.yodel.co.uk/tracking?trackingNumber=JD0123456789012345") is True
    assert t.detect("https://yodel.co.uk/tracking") is True
    # Negative samples
    assert t.detect("INVALID") is False
    assert t.detect("") is False
    # DHL eCommerce range (20 chars: JD + 18 digits) — must NOT be detected by Yodel
    assert t.detect("JD0123456789012345678") is False


def test_class_attributes() -> None:
    """Verify class metadata is correctly declared."""
    assert YodelTracker.name == "yodel"
    assert YodelTracker.priority == 65
    assert YodelTracker.country_codes == ["GB"]


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
    """Parser correctly maps Yodel HTML fixtures to canonical TrackingResult."""
    html = (fixtures_dir / "trackers" / "yodel" / fixture_file).read_text()

    mock_client = AsyncMock(spec=HttpClient)
    mock_client.get = AsyncMock(return_value=_make_response_mock(200, html))

    tracker = YodelTracker(http_client=mock_client)
    result = await tracker.fetch("JD0123456789012345")

    assert result.tracking_number == "JD0123456789012345"
    assert result.found is True
    assert result.carrier_name == "Yodel"
    assert result.carrier_code == "yodel"
    assert result.status is expected_status
    assert len(result.events) >= expected_events_min
    # last_event populated from first parsed event
    assert result.last_event is not None
    assert result.last_event_time is not None
    # Tracker uses the configured TRACK_URL with `trackingNumber` param
    mock_client.get.assert_awaited_once()
    call_args = mock_client.get.await_args
    assert call_args.args[0] == YodelTracker.TRACK_URL
    assert call_args.kwargs["params"] == {"trackingNumber": "JD0123456789012345"}


@pytest.mark.asyncio
async def test_fetch_handles_http_error() -> None:
    """HTTP 500 → returns found=False with error string, no crash."""
    mock_client = AsyncMock(spec=HttpClient)
    mock_client.get = AsyncMock(return_value=_make_response_mock(500, ""))

    tracker = YodelTracker(http_client=mock_client)
    result = await tracker.fetch("JD0123456789012345")

    assert result.found is False
    assert result.error is not None
    assert "500" in result.error


@pytest.mark.asyncio
async def test_fetch_handles_not_found_fixture(fixtures_dir: Path) -> None:
    """An error/not-found page returns found=False without crashing."""
    html = (fixtures_dir / "trackers" / "yodel" / "not_found.html").read_text()

    mock_client = AsyncMock(spec=HttpClient)
    mock_client.get = AsyncMock(return_value=_make_response_mock(200, html))

    tracker = YodelTracker(http_client=mock_client)
    result = await tracker.fetch("JD0123456789012345")

    assert result.found is False
    assert result.tracking_number == "JD0123456789012345"
    assert result.carrier_name == "Yodel"


@pytest.mark.asyncio
async def test_fetch_handles_network_exception() -> None:
    """Network error → returns found=False with error string, no crash."""
    mock_client = AsyncMock(spec=HttpClient)
    mock_client.get = AsyncMock(side_effect=RuntimeError("connection refused"))

    tracker = YodelTracker(http_client=mock_client)
    result = await tracker.fetch("JD0123456789012345")

    assert result.found is False
    assert result.error is not None
    assert "connection refused" in result.error
