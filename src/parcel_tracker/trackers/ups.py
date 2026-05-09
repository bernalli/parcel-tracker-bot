"""UPS Express tracker (web scraping). Synthetic fixtures used for tests; selectors may need tuning at deploy time on real HTML."""

from __future__ import annotations

import logging
import re
from typing import ClassVar

from bs4 import BeautifulSoup

from parcel_tracker.core.http_client import HttpClient
from parcel_tracker.core.tracker_base import AbstractTracker, TrackingResult
from parcel_tracker.db.models import ShipmentStatus, TrackingEvent

logger = logging.getLogger(__name__)


# Multi-locale status keywords (EN/IT/PT/FR/DE/ES) for UPS terminology.
_STATUS_KEYWORDS: dict[ShipmentStatus, tuple[str, ...]] = {
    ShipmentStatus.DELIVERED: (
        "delivered",
        "consegnato",
        "entregue",
        "livré",
        "zugestellt",
        "entregado",
    ),
    ShipmentStatus.OUT_FOR_DELIVERY: (
        "out for delivery",
        "in consegna",
        "saiu para entrega",
        "en cours de livraison",
        "in zustellung",
        "en reparto",
    ),
    ShipmentStatus.IN_TRANSIT: (
        "in transit",
        "in transito",
        "em trânsito",
        "en transit",
        "unterwegs",
        "en tránsito",
    ),
    ShipmentStatus.EXCEPTION: (
        "exception",
        "eccezione",
        "exceção",
        "anomalie",
        "ausnahme",
        "excepción",
    ),
    ShipmentStatus.ALERT: ("alert", "avviso", "alerta", "alerte", "warnung"),
    ShipmentStatus.RETURNED: ("returned", "restituito", "devolvido", "retourné", "zurückgesandt"),
    ShipmentStatus.PICKUP: ("origin scan", "picked up", "ritirato", "abgeholt"),
}


class UpsTracker(AbstractTracker):
    """UPS Express scraper (Tier S, priority 90)."""

    name: ClassVar[str] = "ups"
    priority: ClassVar[int] = 90
    country_codes: ClassVar[list[str]] = ["US", "GLOBAL"]
    tracking_id_patterns: ClassVar[list[re.Pattern[str]]] = [
        re.compile(r"^1Z[A-Z0-9]{16}$"),  # UPS standard 18-char "1Z" prefix
    ]
    url_patterns: ClassVar[list[re.Pattern[str]]] = [
        re.compile(r"ups\.com.*tracknum=", re.IGNORECASE),
    ]

    TRACK_URL: ClassVar[str] = "https://www.ups.com/track"

    def __init__(self, *, http_client: HttpClient | None = None) -> None:
        self._http_client = http_client or HttpClient(timeout=30.0)

    async def fetch(self, tracking_id: str) -> TrackingResult:
        normalized = tracking_id.upper().strip()
        try:
            response = await self._http_client.get(
                self.TRACK_URL,
                params={"tracknum": normalized},
            )
        except Exception as exc:  # noqa: BLE001 (instrumentation: any error → not found)
            logger.warning(
                "UPS fetch failed for %s: %s",
                normalized,
                exc,
                extra={"tracker": self.name, "tracking_id": normalized},
            )
            return TrackingResult(
                tracking_number=normalized,
                found=False,
                carrier_name="UPS",
                error=str(exc),
            )

        if response.status_code != 200:
            return TrackingResult(
                tracking_number=normalized,
                found=False,
                carrier_name="UPS",
                error=f"HTTP {response.status_code}",
            )

        return self._parse_html(normalized, response.text)

    def _parse_html(self, tracking_id: str, html: str) -> TrackingResult:
        soup = BeautifulSoup(html, "lxml")

        events: list[TrackingEvent] = []
        for row in soup.select(".activity-row, .ups-activity-row, tr.activity"):
            date_el = row.select_one(".activity-date, .activity-time, .date, td:nth-child(1)")
            loc_el = row.select_one(".activity-location, .location, td:nth-child(2)")
            desc_el = row.select_one(
                ".activity-description, .activity-status, .description, td:nth-child(3)"
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
                    carrier="UPS",
                )
            )

        if not events:
            return TrackingResult(
                tracking_number=tracking_id,
                found=False,
                carrier_name="UPS",
            )

        status_el = soup.select_one(".package-status, .tracking-status, .shipment-status")
        status_raw = status_el.get_text(strip=True) if status_el else events[0].description
        status = self._map_status(status_raw)

        return TrackingResult(
            tracking_number=tracking_id,
            found=True,
            carrier_name="UPS",
            carrier_code="ups",
            status=status,
            last_event=events[0].description,
            last_event_time=events[0].time,
            events=events,
        )

    @staticmethod
    def _map_status(raw: str) -> ShipmentStatus:
        text = raw.lower()
        # Order matters: "out for delivery" must be checked before "delivered"
        # to avoid the substring 'delivery' matching the DELIVERED branch.
        for status in (
            ShipmentStatus.OUT_FOR_DELIVERY,
            ShipmentStatus.DELIVERED,
            ShipmentStatus.IN_TRANSIT,
            ShipmentStatus.RETURNED,
            ShipmentStatus.EXCEPTION,
            ShipmentStatus.ALERT,
            ShipmentStatus.PICKUP,
        ):
            for keyword in _STATUS_KEYWORDS[status]:
                if keyword in text:
                    return status
        return ShipmentStatus.IN_TRANSIT
