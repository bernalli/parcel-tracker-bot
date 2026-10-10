"""DHL Shipment Tracking (Unified) API tracker."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import respx

from parcel_tracker.core.http_client import HttpClient
from parcel_tracker.core.tracker_base import FetchError
from parcel_tracker.db.models import ShipmentStatus
from parcel_tracker.trackers.dhl_api import DhlApiTracker, map_status


@pytest.fixture
def tracker() -> DhlApiTracker:
    return DhlApiTracker(api_key="k", http_client=HttpClient(timeout=5.0, retry_profile=None))


def test_detection_and_priority() -> None:
    t = DhlApiTracker(api_key="k")
    assert t.priority > 90  # official data runs before every scraper
    for code in ("1234567890", "JD014600006281234567", "00340434161094042557", "RR123456785DE"):
        assert t.detect(code), code
    assert not t.detect("1Z999AA10123456784")
    assert not t.detect("TBA123456789012")


async def test_fetch_parses_express_shipment(tracker: DhlApiTracker, fixtures_dir: Path) -> None:
    payload = json.loads((fixtures_dir / "dhl_api" / "express_in_transit.json").read_text())
    with respx.mock(assert_all_called=True) as mock:
        route = mock.get(DhlApiTracker.API_URL).respond(200, json=payload)
        result = await tracker.fetch("1234567890")
    request = route.calls.last.request
    assert request.headers["DHL-API-Key"] == "k"
    assert request.url.params["trackingNumber"] == "1234567890"
    assert result.found
    assert result.status is ShipmentStatus.OUT_FOR_DELIVERY
    assert result.carrier_name == "DHL Express"
    assert result.last_location == "BERGAMO - ITALY, IT"
    assert len(result.events) == 3
    assert result.events[1].location == "LEIPZIG - GERMANY, DE"


@pytest.mark.parametrize(
    ("status", "kind"),
    [(404, FetchError.NOT_FOUND), (401, FetchError.PERMANENT), (429, FetchError.RATE_LIMITED)],
)
async def test_http_errors(tracker: DhlApiTracker, status: int, kind: FetchError) -> None:
    with respx.mock() as mock:
        mock.get(DhlApiTracker.API_URL).respond(status, json={"title": "x"})
        result = await tracker.fetch("1234567890")
    assert not result.found
    assert result.error_kind is kind


async def test_non_json_is_transient(tracker: DhlApiTracker) -> None:
    with respx.mock() as mock:
        mock.get(DhlApiTracker.API_URL).respond(200, text="<html>")
        result = await tracker.fetch("1234567890")
    assert result.error_kind is FetchError.TRANSIENT


@pytest.mark.parametrize(
    ("code", "text", "expected"),
    [
        ("pre-transit", "Shipment information received", ShipmentStatus.INFO_RECEIVED),
        ("transit", "Processed at hub", ShipmentStatus.IN_TRANSIT),
        ("transit", "Clearance processing complete at customs", ShipmentStatus.CUSTOMS),
        ("delivered", "Delivered - signed for by: ADA", ShipmentStatus.DELIVERED),
        ("failure", "Could not be delivered - recipient absent", ShipmentStatus.UNDELIVERED),
        ("failure", "Returned to shipper", ShipmentStatus.RETURNED),
        ("failure", "Address problem", ShipmentStatus.EXCEPTION),
        ("unknown", "", ShipmentStatus.NOT_FOUND),
    ],
)
def test_status_mapping(code: str, text: str, expected: ShipmentStatus) -> None:
    assert map_status(code, text) is expected


def test_empty_or_malformed_payload() -> None:
    assert not DhlApiTracker.parse("X", {}).found
    assert not DhlApiTracker.parse("X", {"shipments": []}).found
    assert not DhlApiTracker.parse("X", ["nope"]).found
    minimal = DhlApiTracker.parse("X", {"shipments": [{"status": {"statusCode": "delivered"}}]})
    assert minimal.found
    assert minimal.status is ShipmentStatus.DELIVERED
    assert minimal.carrier_name == "DHL"
