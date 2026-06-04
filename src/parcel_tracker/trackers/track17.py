"""17track.net universal tracking fallback.

This is a low-priority (1) tracker that matches ANY tracking_id:
the registry will only fall back to it if no specific tracker matches.
"""

from __future__ import annotations

import logging
import re
from typing import Any, ClassVar

from parcel_tracker.core.http_client import HttpClient
from parcel_tracker.core.tracker_base import AbstractTracker, TrackingResult
from parcel_tracker.db.models import ShipmentStatus, TrackingEvent

logger = logging.getLogger(__name__)


def _fmt_location(address: dict[str, Any] | None) -> str | None:
    """Build a 'City, Country' string from a 17track address object; None if empty."""
    if not address:
        return None
    city = (address.get("city") or "").strip()
    country = (address.get("country") or address.get("country_iso") or "").strip()
    parts = [p for p in (city, country) if p]
    return ", ".join(parts) or None


_STATUS_MAP: dict[str, ShipmentStatus] = {
    "NotFound": ShipmentStatus.NOT_FOUND,
    "InfoReceived": ShipmentStatus.INFO_RECEIVED,
    "PickedUp": ShipmentStatus.PICKUP,
    "InTransit": ShipmentStatus.IN_TRANSIT,
    "OutForDelivery": ShipmentStatus.OUT_FOR_DELIVERY,
    "Delivered": ShipmentStatus.DELIVERED,
    "Undelivered": ShipmentStatus.UNDELIVERED,
    "Alert": ShipmentStatus.ALERT,
    "Exception": ShipmentStatus.EXCEPTION,
    "DeliveryFailure": ShipmentStatus.UNDELIVERED,
    "AvailableForPickup": ShipmentStatus.IN_TRANSIT,
    "Returned": ShipmentStatus.RETURNED,
    "Returning": ShipmentStatus.RETURNED,
    "Expired": ShipmentStatus.EXPIRED,
}


class Track17Tracker(AbstractTracker):
    """
    Universal fallback via 17track.net API v2.2.

    Detects ANY tracking ID (priority 1 = lowest, only used when no specific
    tracker matched). Quarantine via core/health.py shields the bot from the
    infinite-loop bug seen in the legacy `tracker.py`.
    """

    name: ClassVar[str] = "track17"
    priority: ClassVar[int] = 1
    country_codes: ClassVar[list[str]] = []
    tracking_id_patterns: ClassVar[list[re.Pattern[str]]] = [re.compile(r".+")]
    url_patterns: ClassVar[list[re.Pattern[str]]] = []

    REGISTER_URL: ClassVar[str] = "https://api.17track.net/track/v2.2/register"
    STATUS_URL: ClassVar[str] = "https://api.17track.net/track/v2.2/gettrackinfo"

    def __init__(self, api_key: str, *, http_client: HttpClient | None = None) -> None:
        self._api_key = api_key
        self._http_client = http_client or HttpClient(timeout=30.0)

    @property
    def _headers(self) -> dict[str, str]:
        return {
            "Content-Type": "application/json",
            "17token": self._api_key,
            "Accept": "application/json",
        }

    async def fetch(self, tracking_id: str) -> TrackingResult:
        normalized = tracking_id.upper().strip()
        try:
            await self._register(normalized)
            return await self._gettrackinfo(normalized)
        except Exception as exc:  # noqa: BLE001 (instrumentation: any error → return not-found result)
            logger.exception(
                "track17 fetch failed for %s",
                normalized,
                extra={"tracker": self.name, "tracking_id": normalized},
            )
            return TrackingResult(tracking_number=normalized, found=False, error=str(exc))

    async def _register(self, tracking_id: str) -> None:
        """Register the tracking ID with 17track (idempotent server-side)."""
        payload = [{"number": tracking_id}]
        await self._http_client.post(self.REGISTER_URL, json=payload, headers=self._headers)

    async def _gettrackinfo(self, tracking_id: str) -> TrackingResult:
        payload = [{"number": tracking_id}]
        response = await self._http_client.post(
            self.STATUS_URL, json=payload, headers=self._headers
        )
        data: dict[str, Any] = response.json()
        accepted = data.get("data", {}).get("accepted", []) or []
        if not accepted:
            return TrackingResult(tracking_number=tracking_id, found=False)

        item = accepted[0]
        track_info = item.get("track_info") or {}
        latest = track_info.get("latest_status") or {}
        latest_event = track_info.get("latest_event") or {}
        providers = (track_info.get("tracking") or {}).get("providers") or []

        events: list[TrackingEvent] = []
        for provider in providers:
            provider_name = (provider.get("provider") or {}).get("name")
            for evt in provider.get("events") or []:
                events.append(
                    TrackingEvent(
                        time=evt.get("time_iso", ""),
                        description=evt.get("description", ""),
                        location=_fmt_location(evt.get("address")),
                        carrier=provider_name,
                    )
                )

        return TrackingResult(
            tracking_number=tracking_id,
            found=True,
            status=_STATUS_MAP.get(latest.get("status", ""), ShipmentStatus.NOT_FOUND),
            last_event=latest_event.get("description"),
            last_event_time=latest_event.get("time_iso"),
            last_location=_fmt_location(latest_event.get("address")),
            events=events,
            origin=(track_info.get("shipping_info", {}).get("shipper_address") or {}).get(
                "country"
            ),
            destination=(track_info.get("shipping_info", {}).get("recipient_address") or {}).get(
                "country"
            ),
        )
