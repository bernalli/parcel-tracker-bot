"""DHL via the official Shipment Tracking – Unified API (DHL Developer Portal).

One endpoint covers DHL Express, DHL Paket / Deutsche Post (parcel-de), DHL
eCommerce and most other DHL divisions. Registered only when ``DHL_API_KEY`` is
set; it then runs before the DHL and Deutsche Post scrapers, which stay as a
fallback (as does 17track).

Free plan limits (2026): 250 calls per day, about one call per 5 seconds; set
``RATE_LIMIT_TRACKER_DHL_API`` to stay under them.
"""

from __future__ import annotations

import logging
import re
from typing import Any, ClassVar

from parcel_tracker.core.event_status import is_negated_delivery, status_from_text
from parcel_tracker.core.http_client import HttpClient
from parcel_tracker.core.tracker_base import (
    AbstractTracker,
    FetchError,
    TrackingResult,
    classify_exception,
    classify_status,
    last_location_from,
)
from parcel_tracker.db.models import ShipmentStatus, TrackingEvent

logger = logging.getLogger(__name__)

_SERVICE_NAMES: dict[str, str] = {
    "express": "DHL Express",
    "parcel-de": "DHL Paket",
    "parcel-nl": "DHL Parcel NL",
    "parcel-pl": "DHL Parcel PL",
    "parcel-uk": "DHL Parcel UK",
    "ecommerce": "DHL eCommerce",
    "ecommerce-europe": "DHL eCommerce Europe",
    "freight": "DHL Freight",
    "dgf": "DHL Global Forwarding",
    "post-de": "Deutsche Post",
    "sameday": "DHL Same Day",
}

# Refinements of the coarse "transit"/"failure" codes from the event text.
_TRANSIT_REFINEMENTS = frozenset(
    {ShipmentStatus.OUT_FOR_DELIVERY, ShipmentStatus.CUSTOMS, ShipmentStatus.PICKUP}
)
_FAILURE_REFINEMENTS = frozenset(
    {ShipmentStatus.RETURNED, ShipmentStatus.UNDELIVERED, ShipmentStatus.CUSTOMS}
)


def _location(node: dict[str, Any] | None) -> str | None:
    """'City, CC' from a DHL location node ('Bonn, DE'); None when empty."""
    address = ((node or {}).get("location") or {}).get("address") or {}
    locality = str(address.get("addressLocality") or "").strip()
    country = str(address.get("countryCode") or "").strip().upper()
    if locality and country and not locality.upper().endswith(country):
        return f"{locality}, {country}"
    return locality or country or None


def _event_text(node: dict[str, Any]) -> str:
    return str(node.get("description") or node.get("status") or "").strip()


def map_status(code: str | None, text: str) -> ShipmentStatus:
    """Map DHL's statusCode (pre-transit/transit/delivered/failure/unknown)."""
    code = (code or "").lower()
    if code == "delivered":
        return ShipmentStatus.DELIVERED
    if code == "pre-transit":
        return ShipmentStatus.INFO_RECEIVED
    if code == "transit":
        refined = status_from_text(text)
        return refined if refined in _TRANSIT_REFINEMENTS else ShipmentStatus.IN_TRANSIT
    if code == "failure":
        if is_negated_delivery(text):
            return ShipmentStatus.UNDELIVERED
        refined = status_from_text(text)
        return refined if refined in _FAILURE_REFINEMENTS else ShipmentStatus.EXCEPTION
    return ShipmentStatus.NOT_FOUND


class DhlApiTracker(AbstractTracker):
    """DHL Unified Tracking API (official, needs DHL_API_KEY)."""

    name: ClassVar[str] = "dhl_api"
    priority: ClassVar[int] = 95
    country_codes: ClassVar[list[str]] = ["DE", "GLOBAL"]
    tracking_id_patterns: ClassVar[list[re.Pattern[str]]] = [
        re.compile(r"^\d{10}$"),  # DHL Express waybill
        re.compile(r"^JD\d{18}$"),  # DHL eCommerce / Express piece ID
        re.compile(r"^JJD\d{10,30}$"),  # DHL Parcel piece ID
        re.compile(r"^\d{20}$"),  # DHL Paket / Deutsche Post domestic barcode
        re.compile(r"^[A-Z]{2}\d{9}DE$"),  # UPU items issued by Deutsche Post
        re.compile(r"^(?!TBA)[A-Z]{3}\d{9,12}$"),  # DHL Global Mail / eCommerce
    ]
    url_patterns: ClassVar[list[re.Pattern[str]]] = []

    API_URL: ClassVar[str] = "https://api-eu.dhl.com/track/shipments"

    def __init__(self, api_key: str, *, http_client: HttpClient | None = None) -> None:
        self._api_key = api_key
        self._http_client = http_client or HttpClient(timeout=30.0)

    async def fetch(self, tracking_id: str) -> TrackingResult:
        normalized = tracking_id.upper().strip()
        try:
            response = await self._http_client.get(
                self.API_URL,
                params={"trackingNumber": normalized},
                headers={"DHL-API-Key": self._api_key, "Accept": "application/json"},
            )
        except Exception as exc:  # noqa: BLE001 (instrumentation: any error → not found)
            logger.warning("DHL API fetch failed for %s: %s", normalized, exc)
            return TrackingResult(
                tracking_number=normalized,
                found=False,
                error=str(exc),
                error_kind=classify_exception(exc),
            )
        if response.status_code != 200:  # noqa: PLR2004
            kind = classify_status(response.status_code)
            if response.status_code in (401, 403):  # noqa: PLR2004
                logger.error("DHL API rejected the key (HTTP %s)", response.status_code)
                kind = FetchError.PERMANENT
            return TrackingResult(
                tracking_number=normalized,
                found=False,
                error=f"HTTP {response.status_code}",
                error_kind=kind,
            )
        try:
            payload = response.json()
        except ValueError:
            return TrackingResult(
                tracking_number=normalized,
                found=False,
                error="non-JSON response",
                error_kind=FetchError.TRANSIENT,
            )
        return self.parse(normalized, payload)

    @staticmethod
    def parse(tracking_id: str, payload: Any) -> TrackingResult:
        shipments = payload.get("shipments") if isinstance(payload, dict) else None
        if not shipments or not isinstance(shipments[0], dict):
            return TrackingResult(tracking_number=tracking_id, found=False)
        shipment: dict[str, Any] = shipments[0]
        service = str(shipment.get("service") or "")
        carrier = _SERVICE_NAMES.get(service, "DHL")
        events = [
            TrackingEvent(
                time=str(ev.get("timestamp") or ""),
                description=_event_text(ev),
                location=_location(ev),
                carrier=carrier,
            )
            for ev in shipment.get("events") or []
            if isinstance(ev, dict) and _event_text(ev)
        ]
        latest: dict[str, Any] = shipment.get("status") or {}
        latest_text = _event_text(latest) or (events[0].description if events else "")
        status = map_status(latest.get("statusCode"), latest_text)
        return TrackingResult(
            tracking_number=tracking_id,
            found=True,
            status=status,
            carrier_code="dhl",
            carrier_name=carrier,
            last_event=latest_text or None,
            last_event_time=str(latest.get("timestamp") or "") or None,
            last_location=_location(latest) or last_location_from(events),
            events=events,
        )
