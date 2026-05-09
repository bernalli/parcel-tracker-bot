"""Correios (Brazil) tracker (web scraping). Synthetic fixtures used for tests; selectors may need tuning at deploy time on real HTML."""

from __future__ import annotations

import logging
import re
from typing import ClassVar

from bs4 import BeautifulSoup

from parcel_tracker.core.http_client import HttpClient
from parcel_tracker.core.tracker_base import AbstractTracker, TrackingResult
from parcel_tracker.db.models import ShipmentStatus, TrackingEvent

logger = logging.getLogger(__name__)


# Multi-locale status keywords (PT-BR primary for Correios, plus EN/ES/FR/DE/IT)
# for cross-border shipments and inbound international parcels handled by Correios.
_STATUS_KEYWORDS: dict[ShipmentStatus, tuple[str, ...]] = {
    ShipmentStatus.DELIVERED: (
        "entregue",
        "objeto entregue",
        "delivered",
        "entregado",
        "zugestellt",
        "consegnato",
        "livré",
    ),
    ShipmentStatus.OUT_FOR_DELIVERY: (
        "saiu para entrega",
        "out for delivery",
        "en reparto",
        "in zustellung",
        "in consegna",
        "en cours de livraison",
    ),
    ShipmentStatus.IN_TRANSIT: (
        "em trânsito",
        "em transito",
        "encaminhado",
        "in transit",
        "en tránsito",
        "en transito",
        "unterwegs",
        "in transito",
        "en cours d'acheminement",
    ),
    ShipmentStatus.EXCEPTION: (
        "exceção",
        "excecao",
        "exception",
        "excepción",
        "ausnahme",
        "eccezione",
        "anomalie",
    ),
    ShipmentStatus.ALERT: (
        "alerta",
        "alert",
        "warnung",
        "avviso",
        "alerte",
    ),
    ShipmentStatus.RETURNED: (
        "devolvido",
        "devolução",
        "returned",
        "return to sender",
        "devuelto",
        "retoure",
        "zurückgesandt",
        "restituito",
        "retour",
        "retourné",
    ),
    ShipmentStatus.PICKUP: (
        "objeto postado",
        "postado",
        "pré-postagem",
        "pre-postagem",
        "picked up",
        "item received",
        "sender despatching",
        "admitido",
        "abgeholt",
        "ritirato",
        "pris en charge",
    ),
}


class CorreiosTracker(AbstractTracker):
    """Correios (Brazil) scraper (Tier S, priority 75)."""

    name: ClassVar[str] = "correios"
    priority: ClassVar[int] = 75
    country_codes: ClassVar[list[str]] = ["BR"]
    tracking_id_patterns: ClassVar[list[re.Pattern[str]]] = [
        re.compile(r"^[A-Z]{2}\d{9}BR$"),  # UPU BR
    ]
    url_patterns: ClassVar[list[re.Pattern[str]]] = [
        re.compile(r"correios\.com\.br/(sistemas/rastreamento|rastreamento)", re.IGNORECASE),
    ]

    TRACK_URL: ClassVar[str] = "https://www2.correios.com.br/sistemas/rastreamento/resultado.cfm"

    def __init__(self, *, http_client: HttpClient | None = None) -> None:
        self._http_client = http_client or HttpClient(timeout=30.0)

    async def fetch(self, tracking_id: str) -> TrackingResult:
        normalized = tracking_id.upper().strip()
        try:
            response = await self._http_client.get(
                self.TRACK_URL,
                params={"objetos": normalized},
            )
        except Exception as exc:  # noqa: BLE001 (instrumentation: any error → not found)
            logger.warning(
                "Correios fetch failed for %s: %s",
                normalized,
                exc,
                extra={"tracker": self.name, "tracking_id": normalized},
            )
            return TrackingResult(
                tracking_number=normalized,
                found=False,
                carrier_name="Correios",
                error=str(exc),
            )

        if response.status_code != 200:
            return TrackingResult(
                tracking_number=normalized,
                found=False,
                carrier_name="Correios",
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
                    carrier="Correios",
                )
            )

        if not events:
            return TrackingResult(
                tracking_number=tracking_id,
                found=False,
                carrier_name="Correios",
            )

        status_el = soup.select_one(
            ".tracking-status, .delivery-status, .shipment-status, .package-status"
        )
        status_raw = status_el.get_text(strip=True) if status_el else events[0].description
        status = self._map_status(status_raw)

        return TrackingResult(
            tracking_number=tracking_id,
            found=True,
            carrier_name="Correios",
            carrier_code="correios",
            status=status,
            last_event=events[0].description,
            last_event_time=events[0].time,
            events=events,
        )

    @staticmethod
    def _map_status(raw: str) -> ShipmentStatus:
        text = raw.lower()
        # Order matters: "out for delivery" / "saiu para entrega" must be checked
        # before DELIVERED because in some locales / phrasings "delivered" can
        # appear as a substring of out-for-delivery descriptions.
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
