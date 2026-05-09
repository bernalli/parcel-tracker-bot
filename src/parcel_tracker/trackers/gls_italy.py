"""GLS Italy tracker.

Refactored from parcel-tracker-bot/scraper.py:GLSScraper.
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


class GlsItalyTracker(AbstractTracker):
    """GLS Italy scraper — gls-italy.com AJAX endpoint."""

    name: ClassVar[str] = "gls_italy"
    priority: ClassVar[int] = 80
    country_codes: ClassVar[list[str]] = ["IT"]
    tracking_id_patterns: ClassVar[list[re.Pattern[str]]] = [
        re.compile(r"^\d{11,12}$"),  # 11-12 digit numeric (GLS Italy standard)
    ]
    url_patterns: ClassVar[list[re.Pattern[str]]] = []

    TRACK_URL: ClassVar[str] = "https://www.gls-italy.com/track_e_trace_ajax.php"

    def __init__(self, *, http_client: HttpClient | None = None) -> None:
        self._http_client = http_client or HttpClient(timeout=30.0)

    async def fetch(self, tracking_id: str) -> TrackingResult:
        normalized = tracking_id.upper().strip()
        try:
            response = await self._http_client.post(
                self.TRACK_URL,
                data={
                    "r": "track",
                    "localization": "it",
                    "parcel_number": normalized,
                },
            )
        except Exception as exc:  # noqa: BLE001 (instrumentation)
            logger.warning("GLS Italy fetch failed for %s: %s", normalized, exc)
            return TrackingResult(
                tracking_number=normalized,
                found=False,
                carrier_name="GLS Italy",
                error=str(exc),
            )

        if response.status_code != 200:
            return TrackingResult(
                tracking_number=normalized,
                found=False,
                carrier_name="GLS Italy",
                error=f"HTTP {response.status_code}",
            )

        return self._parse_html(normalized, response.text)

    def _parse_html(self, tracking_id: str, html: str) -> TrackingResult:
        soup = BeautifulSoup(html, "lxml")
        events: list[TrackingEvent] = []

        for row in soup.select("tr.riga_tracking, .tracking-row, tr"):
            cells = row.select("td")
            if len(cells) < 3:
                continue
            description = cells[2].get_text(strip=True)
            if not description:
                continue
            events.append(
                TrackingEvent(
                    time=cells[0].get_text(strip=True),
                    description=description,
                    location=cells[1].get_text(strip=True) or None,
                    carrier="GLS Italy",
                )
            )

        if not events:
            return TrackingResult(
                tracking_number=tracking_id,
                found=False,
                carrier_name="GLS Italy",
            )

        return TrackingResult(
            tracking_number=tracking_id,
            found=True,
            carrier_name="GLS Italy",
            carrier_code="gls_italy",
            events=events,
            last_event=events[0].description,
            last_event_time=events[0].time,
        )
