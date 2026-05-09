"""Tests for trackers.evri — Evri (formerly Hermes UK) Tier S scraper."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from parcel_tracker.core.http_client import HttpClient
from parcel_tracker.db.models import ShipmentStatus
from parcel_tracker.trackers.evri import EvriTracker


def test_detects_evri_pattern() -> None:
    """Evri detect: H\\d{15} (legacy Hermes), T\\d{16} (new Evri), \\d{16} (numeric variant), evri.com URLs.

    Note: 16-digit numeric collides with Canada Post (priority=80, wins on tie). Acceptable per spec.
    """
    t = EvriTracker()
    # Positive samples — Evri / legacy Hermes formats
    assert t.detect("H123456789012345") is True  # 16 chars, H + 15 digits (Hermes legacy)
    assert t.detect("T0123456789012345") is True  # 17 chars, T + 16 digits (Evri new)
    assert t.detect("1234567890123456") is True  # 16-digit numeric (Evri variant)
    # URL patterns
    assert t.detect("https://www.evri.com/track?id=T0123456789012345") is True
    assert t.detect("https://hermes-europe.com/tracking") is True
    # Negative samples
    assert t.detect("INVALID") is False
    assert t.detect("") is False
    assert t.detect("AB123456789GB") is False  # Royal Mail-like


def test_class_attributes() -> None:
    """Verify class metadata is correctly declared."""
    assert EvriTracker.name == "evri"
    assert EvriTracker.priority == 65
    assert EvriTracker.country_codes == ["GB"]


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
    """Parser correctly maps Evri HTML fixtures to canonical TrackingResult."""
    html = (fixtures_dir / "trackers" / "evri" / fixture_file).read_text()

    mock_client = AsyncMock(spec=HttpClient)
    mock_client.get = AsyncMock(return_value=_make_response_mock(200, html))

    tracker = EvriTracker(http_client=mock_client)
    result = await tracker.fetch("T0123456789012345")

    assert result.tracking_number == "T0123456789012345"
    assert result.found is True
    assert result.carrier_name == "Evri (formerly Hermes)"
    assert result.carrier_code == "evri"
    assert result.status is expected_status
    assert len(result.events) >= expected_events_min
    # last_event populated from first parsed event
    assert result.last_event is not None
    assert result.last_event_time is not None
    # Tracker uses the configured TRACK_URL with `id` querystring param
    mock_client.get.assert_awaited_once()
    call_args = mock_client.get.await_args
    assert call_args.args[0] == EvriTracker.TRACK_URL
    assert call_args.kwargs["params"] == {"id": "T0123456789012345"}


@pytest.mark.asyncio
async def test_fetch_handles_http_error() -> None:
    """HTTP 500 → returns found=False with error string, no crash."""
    mock_client = AsyncMock(spec=HttpClient)
    mock_client.get = AsyncMock(return_value=_make_response_mock(500, ""))

    tracker = EvriTracker(http_client=mock_client)
    result = await tracker.fetch("T0123456789012345")

    assert result.found is False
    assert result.error is not None
    assert "500" in result.error


@pytest.mark.asyncio
async def test_fetch_handles_not_found_fixture(fixtures_dir: Path) -> None:
    """An error/not-found page returns found=False without crashing."""
    html = (fixtures_dir / "trackers" / "evri" / "not_found.html").read_text()

    mock_client = AsyncMock(spec=HttpClient)
    mock_client.get = AsyncMock(return_value=_make_response_mock(200, html))

    tracker = EvriTracker(http_client=mock_client)
    result = await tracker.fetch("T0123456789012345")

    assert result.found is False
    assert result.tracking_number == "T0123456789012345"
    assert result.carrier_name == "Evri (formerly Hermes)"


@pytest.mark.asyncio
async def test_fetch_handles_network_exception() -> None:
    """Network error → returns found=False with error string, no crash."""
    mock_client = AsyncMock(spec=HttpClient)
    mock_client.get = AsyncMock(side_effect=RuntimeError("connection refused"))

    tracker = EvriTracker(http_client=mock_client)
    result = await tracker.fetch("T0123456789012345")

    assert result.found is False
    assert result.error is not None
    assert "connection refused" in result.error
