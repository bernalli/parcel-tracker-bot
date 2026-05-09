"""SDA tracker.

Refactored from parcel-tracker-bot/scraper.py:PosteItalianeScraper (SDA branch).
SDA is a Poste Italiane subsidiary with its own web portal at www.sda.it.
"""

from __future__ import annotations

import logging
import re
from typing import ClassVar

from bs4 import BeautifulSoup

from parcel_tracker.core.http_client import HttpClient
from parcel_tracker.core.tracker_base import AbstractTracker, TrackingResult
from parcel_tracker.db.models import TrackingEvent

logger = logging.getLogger(__name__)


class SdaTracker(AbstractTracker):
    """SDA (Poste Italiane subsidiary) scraper — www.sda.it endpoint."""

    name: ClassVar[str] = "sda"
    priority: ClassVar[int] = 80
    country_codes: ClassVar[list[str]] = ["IT"]
    tracking_id_patterns: ClassVar[list[re.Pattern[str]]] = [
        re.compile(r"^\d{12,13}$"),  # 12-13 digit numeric
        re.compile(r"^[A-Z]{2}\d{8,11}$"),  # letter-prefix variants
    ]
    url_patterns: ClassVar[list[re.Pattern[str]]] = []

    TRACK_URL: ClassVar[str] = "https://www.sda.it/wps/portal/Servizi/spedizioni"

    def __init__(self, *, http_client: HttpClient | None = None) -> None:
        self._http_client = http_client or HttpClient(timeout=30.0)

    async def fetch(self, tracking_id: str) -> TrackingResult:
        normalized = tracking_id.upper().strip()
        try:
            response = await self._http_client.get(
                self.TRACK_URL,
                params={"tracking": normalized},
            )
        except Exception as exc:  # noqa: BLE001 (instrumentation)
            logger.warning("SDA fetch failed for %s: %s", normalized, exc)
            return TrackingResult(
                tracking_number=normalized,
                found=False,
                carrier_name="SDA",
                error=str(exc),
            )

        if response.status_code != 200:
            return TrackingResult(
                tracking_number=normalized,
                found=False,
                carrier_name="SDA",
                error=f"HTTP {response.status_code}",
            )

        return self._parse_html(normalized, response.text)

    def _parse_html(self, tracking_id: str, html: str) -> TrackingResult:
        soup = BeautifulSoup(html, "lxml")
        events: list[TrackingEvent] = []

        for row in soup.select("tr.tracking-row, .event-row, tr"):
            cells = row.select("td")
            if len(cells) < 2:
                continue
            description = cells[-1].get_text(strip=True)
            if not description:
                continue
            time_text = cells[0].get_text(strip=True)
            if not re.search(r"\d", time_text):
                # Skip header rows
                continue
            events.append(
                TrackingEvent(
                    time=time_text,
                    description=description,
                    location=cells[1].get_text(strip=True) if len(cells) >= 3 else None,
                    carrier="SDA",
                )
            )

        if not events:
            return TrackingResult(
                tracking_number=tracking_id,
                found=False,
                carrier_name="SDA",
            )

        return TrackingResult(
            tracking_number=tracking_id,
            found=True,
            carrier_name="SDA",
            carrier_code="sda",
            events=events,
            last_event=events[0].description,
            last_event_time=events[0].time,
        )
