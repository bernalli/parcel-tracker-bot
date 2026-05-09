"""Evri (formerly Hermes UK, rebranded 2022) tracker (web scraping). Synthetic fixtures used for tests; selectors may need tuning at deploy time on real HTML."""

from __future__ import annotations

import logging
import re
from typing import ClassVar

from bs4 import BeautifulSoup

from parcel_tracker.core.http_client import HttpClient
from parcel_tracker.core.tracker_base import AbstractTracker, TrackingResult
from parcel_tracker.db.models import ShipmentStatus, TrackingEvent

logger = logging.getLogger(__name__)


# British English status keywords for Evri (UK domestic carrier, formerly Hermes UK).
_STATUS_KEYWORDS: dict[ShipmentStatus, tuple[str, ...]] = {
    ShipmentStatus.DELIVERED: ("delivered",),
    ShipmentStatus.OUT_FOR_DELIVERY: ("out for delivery",),
    ShipmentStatus.IN_TRANSIT: ("in transit", "arrived at", "departed", "sorted"),
    ShipmentStatus.EXCEPTION: ("exception",),
    ShipmentStatus.ALERT: ("alert",),
    ShipmentStatus.RETURNED: ("returned", "return to sender"),
    ShipmentStatus.PICKUP: (
        "picked up",
        "shipment information sent",
        "item received",
        "sender despatching",
    ),
}


class EvriTracker(AbstractTracker):
    """Evri scraper (Tier S, priority 65). Formerly Hermes UK; legacy H<digits> IDs still resolve."""

    name: ClassVar[str] = "evri"
    priority: ClassVar[int] = 65
    country_codes: ClassVar[list[str]] = ["GB"]
    tracking_id_patterns: ClassVar[list[re.Pattern[str]]] = [
        re.compile(r"^H\d{15}$"),  # Hermes legacy 16-char (H + 15 digits)
        re.compile(r"^T\d{16}$"),  # Evri new 17-char (T + 16 digits)
        re.compile(
            r"^\d{16}$"
        ),  # Evri numeric variant 16-digit (collides with Canada Post; CP wins by priority)
    ]
    url_patterns: ClassVar[list[re.Pattern[str]]] = [
        re.compile(r"(evri|hermes-europe)\.com.*track", re.IGNORECASE),
    ]

    TRACK_URL: ClassVar[str] = "https://www.evri.com/track"

    def __init__(self, *, http_client: HttpClient | None = None) -> None:
        self._http_client = http_client or HttpClient(timeout=30.0)

    async def fetch(self, tracking_id: str) -> TrackingResult:
        normalized = tracking_id.upper().strip()
        try:
            response = await self._http_client.get(
                self.TRACK_URL,
                params={"id": normalized},
            )
        except Exception as exc:  # noqa: BLE001 (instrumentation: any error → not found)
            logger.warning(
                "Evri fetch failed for %s: %s",
                normalized,
                exc,
                extra={"tracker": self.name, "tracking_id": normalized},
            )
            return TrackingResult(
                tracking_number=normalized,
                found=False,
                carrier_name="Evri (formerly Hermes)",
                error=str(exc),
            )

        if response.status_code != 200:
            return TrackingResult(
                tracking_number=normalized,
                found=False,
                carrier_name="Evri (formerly Hermes)",
                error=f"HTTP {response.status_code}",
            )

        return self._parse_html(normalized, response.text)

    def _parse_html(self, tracking_id: str, html: str) -> TrackingResult:
        soup = BeautifulSoup(html, "lxml")

        events: list[TrackingEvent] = []
        for row in soup.select(
            ".tracking-event, tr.tracking-event, .tracking-events tr, .shipment-events tr"
        ):
            date_el = row.select_one(".event-date, .tracking-date, .date, td:nth-child(1)")
            loc_el = row.select_one(
                ".event-location, .tracking-location, .location, td:nth-child(2)"
            )
            desc_el = row.select_one(
                ".event-description, .event-status, .tracking-status-text, "
                ".description, td:nth-child(4), td:nth-child(3)"
            )
            if not desc_el:
                continue
            description = desc_el.get_text(strip=True)
            if not description:
                continue
            events.append(
                TrackingEvent(
                    time=date_el.get_text(strip=True) if date_el else "",
                    description=description,
                    location=loc_el.get_text(strip=True) if loc_el else None,
                    carrier="Evri (formerly Hermes)",
                )
            )

        if not events:
            return TrackingResult(
                tracking_number=tracking_id,
                found=False,
                carrier_name="Evri (formerly Hermes)",
            )

        status_el = soup.select_one(
            ".tracking-status, .delivery-status, .shipment-status, .package-status"
        )
        status_raw = status_el.get_text(strip=True) if status_el else events[0].description
        status = self._map_status(status_raw)

        return TrackingResult(
            tracking_number=tracking_id,
            found=True,
            carrier_name="Evri (formerly Hermes)",
            carrier_code="evri",
            status=status,
            last_event=events[0].description,
            last_event_time=events[0].time,
            events=events,
        )

    @staticmethod
    def _map_status(raw: str) -> ShipmentStatus:
        text = raw.lower()
        # Order matters: "out for delivery" must be checked before "delivered"
        # because in some phrasings "delivered" can appear as a substring of
        # out-for-delivery descriptions.
        for status in (
            ShipmentStatus.OUT_FOR_DELIVERY,
            ShipmentStatus.DELIVERED,
            ShipmentStatus.RETURNED,
            ShipmentStatus.IN_TRANSIT,
            ShipmentStatus.EXCEPTION,
            ShipmentStatus.ALERT,
            ShipmentStatus.PICKUP,
        ):
            for keyword in _STATUS_KEYWORDS[status]:
                if keyword in text:
                    return status
        return ShipmentStatus.IN_TRANSIT
