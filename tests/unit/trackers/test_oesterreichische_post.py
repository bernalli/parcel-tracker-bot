"""Tests for trackers.oesterreichische_post — Österreichische Post (Austria) Tier S scraper."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from parcel_tracker.core.http_client import HttpClient
from parcel_tracker.db.models import ShipmentStatus
from parcel_tracker.trackers.oesterreichische_post import OesterreichischePostTracker


def test_detects_oesterreichische_post_pattern() -> None:
    """Detect: UPU AT-suffix, Austrian Post 12/14-digit, post.at/sv/sendungssuche URLs."""
    t = OesterreichischePostTracker()
    # Positive samples
    assert t.detect("RR123456789AT") is True  # UPU AT-suffix
    assert t.detect("AB987654321AT") is True  # UPU AT-suffix variant
    assert t.detect("123456789012") is True  # 12-digit Austrian Post
    assert t.detect("12345678901234") is True  # 14-digit Austrian Post
    # URL patterns
    assert t.detect("https://www.post.at/sv/sendungssuche?snr=RR123456789AT") is True
    # Negative samples
    assert t.detect("INVALID") is False
    assert t.detect("") is False
    assert t.detect("AB123456789DE") is False  # Deutsche Post-like, wrong country


def test_class_attributes() -> None:
    """Verify class metadata is correctly declared."""
    assert OesterreichischePostTracker.name == "oesterreichische_post"
    assert OesterreichischePostTracker.priority == 60
    assert OesterreichischePostTracker.country_codes == ["AT"]


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
    """Parser correctly maps Österreichische Post HTML fixtures to canonical TrackingResult."""
    html = (fixtures_dir / "trackers" / "oesterreichische_post" / fixture_file).read_text()

    mock_client = AsyncMock(spec=HttpClient)
    mock_client.get = AsyncMock(return_value=_make_response_mock(200, html))

    tracker = OesterreichischePostTracker(http_client=mock_client)
    result = await tracker.fetch("RR123456789AT")

    assert result.tracking_number == "RR123456789AT"
    assert result.found is True
    assert result.carrier_name == "Österreichische Post"
    assert result.carrier_code == "oesterreichische_post"
    assert result.status is expected_status
    assert len(result.events) >= expected_events_min
    # last_event populated from first parsed event
    assert result.last_event is not None
    assert result.last_event_time is not None
    # Tracker uses the configured TRACK_URL with `snr` querystring param
    mock_client.get.assert_awaited_once()
    call_args = mock_client.get.await_args
    assert call_args.args[0] == OesterreichischePostTracker.TRACK_URL
    assert call_args.kwargs["params"] == {"snr": "RR123456789AT"}


@pytest.mark.asyncio
async def test_fetch_handles_http_error() -> None:
    """HTTP 500 → returns found=False with error string, no crash."""
    mock_client = AsyncMock(spec=HttpClient)
    mock_client.get = AsyncMock(return_value=_make_response_mock(500, ""))

    tracker = OesterreichischePostTracker(http_client=mock_client)
    result = await tracker.fetch("RR123456789AT")

    assert result.found is False
    assert result.error is not None
    assert "500" in result.error


@pytest.mark.asyncio
async def test_fetch_handles_not_found_fixture(fixtures_dir: Path) -> None:
    """An error/not-found page returns found=False without crashing."""
    html = (fixtures_dir / "trackers" / "oesterreichische_post" / "not_found.html").read_text()

    mock_client = AsyncMock(spec=HttpClient)
    mock_client.get = AsyncMock(return_value=_make_response_mock(200, html))

    tracker = OesterreichischePostTracker(http_client=mock_client)
    result = await tracker.fetch("RR123456789AT")

    assert result.found is False
    assert result.tracking_number == "RR123456789AT"
    assert result.carrier_name == "Österreichische Post"


@pytest.mark.asyncio
async def test_fetch_handles_network_exception() -> None:
    """Network error → returns found=False with error string, no crash."""
    mock_client = AsyncMock(spec=HttpClient)
    mock_client.get = AsyncMock(side_effect=RuntimeError("connection refused"))

    tracker = OesterreichischePostTracker(http_client=mock_client)
    result = await tracker.fetch("RR123456789AT")

    assert result.found is False
    assert result.error is not None
    assert "connection refused" in result.error
