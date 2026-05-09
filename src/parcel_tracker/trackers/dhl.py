"""DHL Express tracker (web scraping with optional API fallback).

Refactored from parcel-tracker-bot/scraper.py:DHLScraper.
Uses tracking site URL since DHL's open API requires per-customer keys.
"""

from __future__ import annotations

import logging
import re
from typing import ClassVar

from bs4 import BeautifulSoup

from parcel_tracker.core.http_client import HttpClient
from parcel_tracker.core.tracker_base import AbstractTracker, TrackingResult
from parcel_tracker.db.models import ShipmentStatus, TrackingEvent

logger = logging.getLogger(__name__)


class DhlTracker(AbstractTracker):
    """DHL Express scraper."""

    name: ClassVar[str] = "dhl"
    priority: ClassVar[int] = 70
    country_codes: ClassVar[list[str]] = ["DE", "GLOBAL"]
    tracking_id_patterns: ClassVar[list[re.Pattern[str]]] = [
        re.compile(r"^\d{10}$"),  # 10-digit DHL Express
        re.compile(r"^JD\d{18}$"),  # DHL eCommerce
        re.compile(r"^[A-Z]{3}\d{9,12}$"),  # DHL Global Mail / variants
    ]
    url_patterns: ClassVar[list[re.Pattern[str]]] = [
        re.compile(r"dhl\.com.*tracking-id=", re.IGNORECASE),
    ]

    TRACK_URL: ClassVar[str] = "https://www.dhl.com/global-en/home/tracking.html"

    def __init__(self, *, http_client: HttpClient | None = None) -> None:
        self._http_client = http_client or HttpClient(timeout=30.0)

    async def fetch(self, tracking_id: str) -> TrackingResult:
        normalized = tracking_id.upper().strip()
        try:
            response = await self._http_client.get(
                self.TRACK_URL,
                params={"tracking-id": normalized, "submit": "1"},
            )
        except Exception as exc:  # noqa: BLE001 (instrumentation: any error → not found)
            logger.warning(
                "DHL fetch failed for %s: %s",
                normalized,
                exc,
                extra={"tracker": self.name, "tracking_id": normalized},
            )
            return TrackingResult(tracking_number=normalized, found=False, error=str(exc))

        if response.status_code != 200:
            return TrackingResult(
                tracking_number=normalized,
                found=False,
                error=f"HTTP {response.status_code}",
            )

        return self._parse_html(normalized, response.text)

    def _parse_html(self, tracking_id: str, html: str) -> TrackingResult:
        soup = BeautifulSoup(html, "lxml")

        events: list[TrackingEvent] = []
        for event_el in soup.select(".event, .shipment-event"):
            time_el = event_el.select_one(".time, .event-time")
            desc_el = event_el.select_one(".description, .event-description")
            loc_el = event_el.select_one(".location, .event-location")
            if not desc_el:
                continue
            events.append(
                TrackingEvent(
                    time=time_el.get_text(strip=True) if time_el else "",
                    description=desc_el.get_text(strip=True),
                    location=loc_el.get_text(strip=True) if loc_el else None,
                    carrier="DHL",
                )
            )

        if not events:
            return TrackingResult(tracking_number=tracking_id, found=False, carrier_name="DHL")

        status_el = soup.select_one(".status, .tracking-status")
        status_raw = status_el.get_text(strip=True).lower() if status_el else ""
        status = self._map_status(status_raw)

        return TrackingResult(
            tracking_number=tracking_id,
            found=True,
            carrier_name="DHL",
            carrier_code="dhl",
            status=status,
            last_event=events[0].description,
            last_event_time=events[0].time,
            events=events,
        )

    @staticmethod
    def _map_status(raw: str) -> ShipmentStatus:
        raw = raw.lower()
        if "delivered" in raw:
            return ShipmentStatus.DELIVERED
        if "out for delivery" in raw:
            return ShipmentStatus.OUT_FOR_DELIVERY
        if "transit" in raw:
            return ShipmentStatus.IN_TRANSIT
        if "exception" in raw or "alert" in raw:
            return ShipmentStatus.ALERT
        return ShipmentStatus.NOT_FOUND
