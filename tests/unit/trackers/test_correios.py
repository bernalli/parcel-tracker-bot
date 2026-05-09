"""Tests for trackers.correios — Correios (Brazil) Tier S scraper."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from parcel_tracker.core.http_client import HttpClient
from parcel_tracker.db.models import ShipmentStatus
from parcel_tracker.trackers.correios import CorreiosTracker


def test_detects_correios_pattern() -> None:
    """Correios detect: BR UPU IDs and correios.com.br tracking URL."""
    t = CorreiosTracker()
    # Positive samples
    assert t.detect("AB123456789BR") is True  # UPU BR
    assert t.detect("RR987654321BR") is True  # UPU BR (registered)
    assert t.detect("LX555555555BR") is True  # UPU BR (express)
    # URL pattern
    assert (
        t.detect(
            "https://www2.correios.com.br/sistemas/rastreamento/resultado.cfm?objetos=AB123456789BR"
        )
        is True
    )
    assert t.detect("https://www.correios.com.br/rastreamento?objeto=AB123456789BR") is True
    # Negative samples
    assert t.detect("INVALID") is False
    assert t.detect("") is False
    assert t.detect("AB123456789ES") is False  # Correos Spain, wrong country


def test_class_attributes() -> None:
    """Verify class metadata is correctly declared."""
    assert CorreiosTracker.name == "correios"
    assert CorreiosTracker.priority == 75
    assert "BR" in CorreiosTracker.country_codes


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
    """Parser correctly maps Correios HTML fixtures to canonical TrackingResult."""
    html = (fixtures_dir / "trackers" / "correios" / fixture_file).read_text()

    mock_client = AsyncMock(spec=HttpClient)
    mock_client.get = AsyncMock(return_value=_make_response_mock(200, html))

    tracker = CorreiosTracker(http_client=mock_client)
    result = await tracker.fetch("AB123456789BR")

    assert result.tracking_number == "AB123456789BR"
    assert result.found is True
    assert result.carrier_name == "Correios"
    assert result.carrier_code == "correios"
    assert result.status is expected_status
    assert len(result.events) >= expected_events_min
    # last_event populated from first parsed event
    assert result.last_event is not None
    assert result.last_event_time is not None
    # Tracker uses the configured TRACK_URL with `objetos` param
    mock_client.get.assert_awaited_once()
    call_args = mock_client.get.await_args
    assert call_args.args[0] == CorreiosTracker.TRACK_URL
    assert call_args.kwargs["params"] == {"objetos": "AB123456789BR"}


@pytest.mark.asyncio
async def test_fetch_handles_http_error() -> None:
    """HTTP 500 → returns found=False with error string, no crash."""
    mock_client = AsyncMock(spec=HttpClient)
    mock_client.get = AsyncMock(return_value=_make_response_mock(500, ""))

    tracker = CorreiosTracker(http_client=mock_client)
    result = await tracker.fetch("AB123456789BR")

    assert result.found is False
    assert result.error is not None
    assert "500" in result.error


@pytest.mark.asyncio
async def test_fetch_handles_not_found_fixture(fixtures_dir: Path) -> None:
    """An error/not-found page returns found=False without crashing."""
    html = (fixtures_dir / "trackers" / "correios" / "not_found.html").read_text()

    mock_client = AsyncMock(spec=HttpClient)
    mock_client.get = AsyncMock(return_value=_make_response_mock(200, html))

    tracker = CorreiosTracker(http_client=mock_client)
    result = await tracker.fetch("AB123456789BR")

    assert result.found is False
    assert result.tracking_number == "AB123456789BR"
    assert result.carrier_name == "Correios"


@pytest.mark.asyncio
async def test_fetch_handles_network_exception() -> None:
    """Network error → returns found=False with error string, no crash."""
    mock_client = AsyncMock(spec=HttpClient)
    mock_client.get = AsyncMock(side_effect=RuntimeError("connection refused"))

    tracker = CorreiosTracker(http_client=mock_client)
    result = await tracker.fetch("AB123456789BR")

    assert result.found is False
    assert result.error is not None
    assert "connection refused" in result.error
