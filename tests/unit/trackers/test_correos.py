"""Tests for trackers.correos — Correos (Spain) Tier S scraper."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from parcel_tracker.core.http_client import HttpClient
from parcel_tracker.db.models import ShipmentStatus
from parcel_tracker.trackers.correos import CorreosTracker


def test_detects_correos_pattern() -> None:
    """Correos detect: ES UPU IDs and correos.es localizador URL."""
    t = CorreosTracker()
    # Positive samples
    assert t.detect("AB123456789ES") is True  # UPU ES
    assert t.detect("RR987654321ES") is True  # UPU ES (registered)
    assert t.detect("LX555555555ES") is True  # UPU ES (express)
    # URL pattern
    assert (
        t.detect("https://www.correos.es/es/es/herramientas/localizador?codEnvio=AB123456789ES")
        is True
    )
    # Negative samples
    assert t.detect("INVALID") is False
    assert t.detect("") is False
    assert t.detect("AB123456789FR") is False  # wrong country (FR instead of ES)


def test_class_attributes() -> None:
    """Verify class metadata is correctly declared."""
    assert CorreosTracker.name == "correos"
    assert CorreosTracker.priority == 75
    assert "ES" in CorreosTracker.country_codes


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
    """Parser correctly maps Correos HTML fixtures to canonical TrackingResult."""
    html = (fixtures_dir / "trackers" / "correos" / fixture_file).read_text()

    mock_client = AsyncMock(spec=HttpClient)
    mock_client.get = AsyncMock(return_value=_make_response_mock(200, html))

    tracker = CorreosTracker(http_client=mock_client)
    result = await tracker.fetch("AB123456789ES")

    assert result.tracking_number == "AB123456789ES"
    assert result.found is True
    assert result.carrier_name == "Correos"
    assert result.carrier_code == "correos"
    assert result.status is expected_status
    assert len(result.events) >= expected_events_min
    # last_event populated from first parsed event
    assert result.last_event is not None
    assert result.last_event_time is not None
    # Tracker uses the configured TRACK_URL with codEnvio param
    mock_client.get.assert_awaited_once()
    call_args = mock_client.get.await_args
    assert call_args.args[0] == CorreosTracker.TRACK_URL
    assert call_args.kwargs["params"] == {"codEnvio": "AB123456789ES"}


@pytest.mark.asyncio
async def test_fetch_handles_http_error() -> None:
    """HTTP 500 → returns found=False with error string, no crash."""
    mock_client = AsyncMock(spec=HttpClient)
    mock_client.get = AsyncMock(return_value=_make_response_mock(500, ""))

    tracker = CorreosTracker(http_client=mock_client)
    result = await tracker.fetch("AB123456789ES")

    assert result.found is False
    assert result.error is not None
    assert "500" in result.error


@pytest.mark.asyncio
async def test_fetch_handles_not_found_fixture(fixtures_dir: Path) -> None:
    """An error/not-found page returns found=False without crashing."""
    html = (fixtures_dir / "trackers" / "correos" / "not_found.html").read_text()

    mock_client = AsyncMock(spec=HttpClient)
    mock_client.get = AsyncMock(return_value=_make_response_mock(200, html))

    tracker = CorreosTracker(http_client=mock_client)
    result = await tracker.fetch("AB123456789ES")

    assert result.found is False
    assert result.tracking_number == "AB123456789ES"
    assert result.carrier_name == "Correos"


@pytest.mark.asyncio
async def test_fetch_handles_network_exception() -> None:
    """Network error → returns found=False with error string, no crash."""
    mock_client = AsyncMock(spec=HttpClient)
    mock_client.get = AsyncMock(side_effect=RuntimeError("connection refused"))

    tracker = CorreosTracker(http_client=mock_client)
    result = await tracker.fetch("AB123456789ES")

    assert result.found is False
    assert result.error is not None
    assert "connection refused" in result.error
