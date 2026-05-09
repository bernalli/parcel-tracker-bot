"""Swiss Post tracker (web scraping). Synthetic fixtures used for tests; selectors may need tuning at deploy time on real HTML."""

from __future__ import annotations

import logging
import re
from typing import ClassVar

from bs4 import BeautifulSoup

from parcel_tracker.core.http_client import HttpClient
from parcel_tracker.core.tracker_base import AbstractTracker, TrackingResult
from parcel_tracker.db.models import ShipmentStatus, TrackingEvent

logger = logging.getLogger(__name__)


# Multi-locale status keywords for Swiss Post. Switzerland is multilingual, so DE/FR/IT
# are primary; EN secondary for safety.
_STATUS_KEYWORDS: dict[ShipmentStatus, tuple[str, ...]] = {
    ShipmentStatus.DELIVERED: (
        "zugestellt",
        "distribué",
        "distribue",
        "consegnato",
        "delivered",
    ),
    ShipmentStatus.OUT_FOR_DELIVERY: (
        "in zustellung",
        "en cours de distribution",
        "in distribuzione",
        "out for delivery",
    ),
    ShipmentStatus.IN_TRANSIT: (
        "unterwegs",
        "in transit",
        "en cours d'acheminement",
        "en cours d acheminement",
        "in transito",
        "im verteilzentrum",
        "verteilzentrum verlassen",
        "centre de tri",
        "centre de distribution",
        "centro di smistamento",
        "sortiert",
        "sorted",
    ),
    ShipmentStatus.EXCEPTION: (
        "ausnahme",
        "exception",
        "problem",
        "problème",
        "probleme",
        "problema",
    ),
    ShipmentStatus.ALERT: ("warnung", "alert", "alerte", "avviso"),
    ShipmentStatus.RETURNED: (
        "retoure",
        "zurückgesandt",
        "zurueckgesandt",
        "returned",
        "return to sender",
        "retour",
        "retourné",
        "retourne",
        "restituito",
        "ritornato",
    ),
    ShipmentStatus.PICKUP: (
        "übernommen",
        "uebernommen",
        "abgeholt",
        "picked up",
        "shipment information sent",
        "sendungsdaten erhalten",
        "sendungsdaten elektronisch",
        "pris en charge",
        "données électroniques",
        "donnees electroniques",
        "presa in carico",
        "preso in carico",
        "dati elettronici",
    ),
}


class SwissPostTracker(AbstractTracker):
    """Swiss Post scraper (Tier S, priority 60). Switzerland national carrier."""

    name: ClassVar[str] = "swisspost"
    priority: ClassVar[int] = 60
    country_codes: ClassVar[list[str]] = ["CH"]
    tracking_id_patterns: ClassVar[list[re.Pattern[str]]] = [
        re.compile(r"^[A-Z]{2}\d{9}CH$"),  # UPU CH
        re.compile(r"^99\.\d{2}\.\d{6}\.\d{8}$"),  # Swiss Post barcode dotted format
        re.compile(r"^99\d{16}$"),  # Swiss Post alternate 18-digit (99 prefix)
    ]
    url_patterns: ClassVar[list[re.Pattern[str]]] = [
        re.compile(r"service\.post\.ch", re.IGNORECASE),
    ]

    TRACK_URL: ClassVar[str] = "https://service.post.ch/EasyTrack/"

    def __init__(self, *, http_client: HttpClient | None = None) -> None:
        self._http_client = http_client or HttpClient(timeout=30.0)

    async def fetch(self, tracking_id: str) -> TrackingResult:
        normalized = tracking_id.upper().strip()
        try:
            response = await self._http_client.get(
                self.TRACK_URL,
                params={"formattedParcelCodes": normalized},
            )
        except Exception as exc:  # noqa: BLE001 (instrumentation: any error → not found)
            logger.warning(
                "Swiss Post fetch failed for %s: %s",
                normalized,
                exc,
                extra={"tracker": self.name, "tracking_id": normalized},
            )
            return TrackingResult(
                tracking_number=normalized,
                found=False,
                carrier_name="Swiss Post",
                error=str(exc),
            )

        if response.status_code != 200:
            return TrackingResult(
                tracking_number=normalized,
                found=False,
                carrier_name="Swiss Post",
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
                    carrier="Swiss Post",
                )
            )

        if not events:
            return TrackingResult(
                tracking_number=tracking_id,
                found=False,
                carrier_name="Swiss Post",
            )

        status_el = soup.select_one(
            ".tracking-status, .delivery-status, .shipment-status, .package-status"
        )
        status_raw = status_el.get_text(strip=True) if status_el else events[0].description
        status = self._map_status(status_raw)

        return TrackingResult(
            tracking_number=tracking_id,
            found=True,
            carrier_name="Swiss Post",
            carrier_code="swisspost",
            status=status,
            last_event=events[0].description,
            last_event_time=events[0].time,
            events=events,
        )

    @staticmethod
    def _map_status(raw: str) -> ShipmentStatus:
        text = raw.lower()
        # Order matters: OUT_FOR_DELIVERY checked before DELIVERED to avoid spurious
        # match (e.g. "in zustellung" must not be classified as delivered).
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
