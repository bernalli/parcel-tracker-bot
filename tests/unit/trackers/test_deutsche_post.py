"""Tests for trackers.deutsche_post — Deutsche Post Tier S scraper."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from parcel_tracker.core.http_client import HttpClient
from parcel_tracker.db.models import ShipmentStatus
from parcel_tracker.trackers.deutsche_post import DeutschePostTracker


def test_detects_deutsche_post_pattern() -> None:
    """Deutsche Post detect: UPU DE-suffix IDs, 20-digit domestic barcode, deutschepost.de URL."""
    t = DeutschePostTracker()
    # Positive samples
    assert t.detect("RR123456789DE") is True
    assert t.detect("LX987654321DE") is True
    assert t.detect("12345678901234567890") is True
    # URL pattern
    assert (
        t.detect(
            "https://www.deutschepost.de/sendung/simpleQuery.html?form.sendungsnummern=RR123456789DE"
        )
        is True
    )
    # Negative samples
    assert t.detect("INVALID") is False
    assert t.detect("") is False
    assert t.detect("AB123456789FR") is False  # wrong country suffix (La Poste)


def test_class_attributes() -> None:
    """Verify class metadata is correctly declared."""
    assert DeutschePostTracker.name == "deutsche_post"
    assert DeutschePostTracker.priority == 85
    assert "DE" in DeutschePostTracker.country_codes


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
    """Parser correctly maps Deutsche Post HTML fixtures to canonical TrackingResult."""
    html = (fixtures_dir / "trackers" / "deutsche_post" / fixture_file).read_text()

    mock_client = AsyncMock(spec=HttpClient)
    mock_client.get = AsyncMock(return_value=_make_response_mock(200, html))

    tracker = DeutschePostTracker(http_client=mock_client)
    result = await tracker.fetch("RR123456789DE")

    assert result.tracking_number == "RR123456789DE"
    assert result.found is True
    assert result.carrier_name == "Deutsche Post"
    assert result.carrier_code == "deutsche_post"
    assert result.status is expected_status
    assert len(result.events) >= expected_events_min
    # last_event populated from first parsed event
    assert result.last_event is not None
    assert result.last_event_time is not None
    # Tracker uses the configured TRACK_URL with form.sendungsnummern param
    mock_client.get.assert_awaited_once()
    call_args = mock_client.get.await_args
    assert call_args.args[0] == DeutschePostTracker.TRACK_URL
    assert call_args.kwargs["params"] == {"form.sendungsnummern": "RR123456789DE"}


@pytest.mark.asyncio
async def test_fetch_handles_http_error() -> None:
    """HTTP 500 → returns found=False with error string, no crash."""
    mock_client = AsyncMock(spec=HttpClient)
    mock_client.get = AsyncMock(return_value=_make_response_mock(500, ""))

    tracker = DeutschePostTracker(http_client=mock_client)
    result = await tracker.fetch("RR123456789DE")

    assert result.found is False
    assert result.error is not None
    assert "500" in result.error


@pytest.mark.asyncio
async def test_fetch_handles_not_found_fixture(fixtures_dir: Path) -> None:
    """An error/not-found page returns found=False without crashing."""
    html = (fixtures_dir / "trackers" / "deutsche_post" / "not_found.html").read_text()

    mock_client = AsyncMock(spec=HttpClient)
    mock_client.get = AsyncMock(return_value=_make_response_mock(200, html))

    tracker = DeutschePostTracker(http_client=mock_client)
    result = await tracker.fetch("RR123456789DE")

    assert result.found is False
    assert result.tracking_number == "RR123456789DE"
    assert result.carrier_name == "Deutsche Post"


@pytest.mark.asyncio
async def test_fetch_handles_network_exception() -> None:
    """Network error → returns found=False with error string, no crash."""
    mock_client = AsyncMock(spec=HttpClient)
    mock_client.get = AsyncMock(side_effect=RuntimeError("connection refused"))

    tracker = DeutschePostTracker(http_client=mock_client)
    result = await tracker.fetch("RR123456789DE")

    assert result.found is False
    assert result.error is not None
    assert "connection refused" in result.error
