"""Poste Italiane tracker.

Refactored from parcel-tracker-bot/scraper.py:PosteItalianeScraper.
Uses the JSON API at www.poste.it/online/dovequando/ricerca.do.
"""

from __future__ import annotations

import logging
import re
from typing import Any, ClassVar

from parcel_tracker.core.http_client import HttpClient
from parcel_tracker.core.tracker_base import AbstractTracker, TrackingResult
from parcel_tracker.db.models import TrackingEvent

logger = logging.getLogger(__name__)


class PosteItalianeTracker(AbstractTracker):
    """Poste Italiane scraper — JSON API at www.poste.it."""

    name: ClassVar[str] = "poste_italiane"
    priority: ClassVar[int] = 80
    country_codes: ClassVar[list[str]] = ["IT"]
    tracking_id_patterns: ClassVar[list[re.Pattern[str]]] = [
        re.compile(r"^[A-Z]{2}\d{9}[A-Z]{2}$"),  # international format (CC+9d+CC)
        re.compile(r"^\d{23}$"),  # 23-digit barcode
        re.compile(r"^[A-Z0-9]{12,14}$"),  # alphanumeric 12-14 chars
    ]
    url_patterns: ClassVar[list[re.Pattern[str]]] = []

    TRACK_URL: ClassVar[str] = "https://www.poste.it/online/dovequando/ricerca.do"

    def __init__(self, *, http_client: HttpClient | None = None) -> None:
        self._http_client = http_client or HttpClient(timeout=30.0)

    async def fetch(self, tracking_id: str) -> TrackingResult:
        normalized = tracking_id.upper().strip()
        try:
            response = await self._http_client.get(
                self.TRACK_URL,
                params={
                    "action": "ricercaSpedizione",
                    "mpcode": normalized,
                },
            )
        except Exception as exc:  # noqa: BLE001 (instrumentation)
            logger.warning("Poste Italiane fetch failed for %s: %s", normalized, exc)
            return TrackingResult(
                tracking_number=normalized,
                found=False,
                carrier_name="Poste Italiane",
                error=str(exc),
            )

        if response.status_code != 200:
            return TrackingResult(
                tracking_number=normalized,
                found=False,
                carrier_name="Poste Italiane",
                error=f"HTTP {response.status_code}",
            )

        try:
            data: Any = response.json()
        except Exception:  # noqa: BLE001 (instrumentation)
            return TrackingResult(
                tracking_number=normalized,
                found=False,
                carrier_name="Poste Italiane",
                error="Risposta non parsabile",
            )

        return self._parse_json(normalized, data)

    def _parse_json(self, tracking_id: str, data: Any) -> TrackingResult:
        if not isinstance(data, dict):
            return TrackingResult(
                tracking_number=tracking_id,
                found=False,
                carrier_name="Poste Italiane",
            )

        if not data.get("spilesitosped") or data.get("esito") == "KO":
            return TrackingResult(
                tracking_number=tracking_id,
                found=False,
                carrier_name="Poste Italiane",
            )

        events: list[TrackingEvent] = []
        for ev in data.get("listaeventi", []):
            description = ev.get("evento", "")
            if not description:
                continue
            events.append(
                TrackingEvent(
                    time=f"{ev.get('data', '')} {ev.get('ora', '')}".strip(),
                    description=description,
                    location=ev.get("luogo") or None,
                    carrier="Poste Italiane",
                )
            )

        if not events:
            return TrackingResult(
                tracking_number=tracking_id,
                found=False,
                carrier_name="Poste Italiane",
            )

        return TrackingResult(
            tracking_number=tracking_id,
            found=True,
            carrier_name="Poste Italiane",
            carrier_code="poste_italiane",
            events=events,
            last_event=events[0].description,
            last_event_time=events[0].time,
        )
