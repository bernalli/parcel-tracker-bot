"""BRT (Bartolini) tracker.

Refactored from parcel-tracker-bot/scraper.py:BRTScraper.
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


class BrtTracker(AbstractTracker):
    """BRT (Bartolini) scraper — vas.brt.it endpoint."""

    name: ClassVar[str] = "brt"
    priority: ClassVar[int] = 80
    country_codes: ClassVar[list[str]] = ["IT"]
    tracking_id_patterns: ClassVar[list[re.Pattern[str]]] = [
        re.compile(r"^\d{12}$"),  # Numero spedizione
        re.compile(r"^\d{14,15}$"),  # BRTcode standard
        re.compile(r"^\d{19}$"),  # BRTcode esteso
        re.compile(r"^BRT\d{9,12}$"),  # BRT prefix variant
    ]
    url_patterns: ClassVar[list[re.Pattern[str]]] = []

    TRACK_URL: ClassVar[str] = "https://vas.brt.it/vas/sped_det_new.htm"

    def __init__(self, *, http_client: HttpClient | None = None) -> None:
        self._http_client = http_client or HttpClient(timeout=30.0)

    async def fetch(self, tracking_id: str) -> TrackingResult:
        normalized = tracking_id.upper().strip()
        if len(normalized) == 12 and normalized.isdigit():
            params: dict[str, str] = {"Nspediz": normalized}
        else:
            params = {"brtCode": normalized}

        try:
            response = await self._http_client.get(self.TRACK_URL, params=params)
        except Exception as exc:  # noqa: BLE001 (instrumentation)
            logger.warning("BRT fetch failed for %s: %s", normalized, exc)
            return TrackingResult(
                tracking_number=normalized,
                found=False,
                carrier_name="BRT",
                error=str(exc),
            )

        if response.status_code != 200:
            return TrackingResult(
                tracking_number=normalized,
                found=False,
                carrier_name="BRT",
                error=f"HTTP {response.status_code}",
            )

        return self._parse_html(normalized, response.text)

    def _parse_html(self, tracking_id: str, html: str) -> TrackingResult:
        soup = BeautifulSoup(html, "lxml")
        events: list[TrackingEvent] = []

        for row in soup.find_all("tr"):
            cells = row.find_all("td")
            if len(cells) < 3:
                continue
            cell_texts = [c.get_text(strip=True) for c in cells]
            date_idx: int | None = None
            for i, text in enumerate(cell_texts):
                if re.match(r"\d{2}[/.-]\d{2}[/.-]\d{4}", text):
                    date_idx = i
                    break
            if date_idx is None:
                continue
            date_str = cell_texts[date_idx]
            time_str = ""
            desc_start = date_idx + 1
            if desc_start < len(cell_texts) and re.match(
                r"\d{1,2}[:.]\d{2}", cell_texts[desc_start]
            ):
                time_str = cell_texts[desc_start]
                desc_start += 1
            remaining = cell_texts[desc_start:]
            description = (
                remaining[1]
                if len(remaining) >= 2 and re.search(r"\(\d{2,4}\)", remaining[0])
                else (remaining[0] if remaining else "")
            )
            if description:
                events.append(
                    TrackingEvent(
                        time=f"{date_str} {time_str}".strip(),
                        description=description,
                        location=remaining[0]
                        if len(remaining) >= 2 and re.search(r"\(\d{2,4}\)", remaining[0])
                        else (remaining[1] if len(remaining) >= 2 else None),
                        carrier="BRT",
                    )
                )

        if not events:
            return TrackingResult(
                tracking_number=tracking_id,
                found=False,
                carrier_name="BRT",
            )

        return TrackingResult(
            tracking_number=tracking_id,
            found=True,
            carrier_name="BRT",
            carrier_code="brt",
            events=events,
            last_event=events[0].description,
            last_event_time=events[0].time,
        )
