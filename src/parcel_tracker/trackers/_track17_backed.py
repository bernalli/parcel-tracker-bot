"""Track17-backed detection-only tracker base class.

Used for carriers where pattern detection is reliable but scraping is
unfeasible (login-bound, JS-rendered, or simply better served by Track17).
"""

from __future__ import annotations

import logging
from typing import ClassVar

from parcel_tracker.core.tracker_base import AbstractTracker, TrackingResult
from parcel_tracker.trackers.track17 import Track17Tracker

logger = logging.getLogger(__name__)


class Track17BackedTracker(AbstractTracker):
    """Detection-only tracker that delegates fetch to Track17 and rebrands result.

    Subclasses MUST set:
        - name, priority, country_codes, tracking_id_patterns, url_patterns
        - CARRIER_NAME, CARRIER_CODE (used to rebrand the Track17 result)
    """

    CARRIER_NAME: ClassVar[str] = ""
    CARRIER_CODE: ClassVar[str] = ""

    def __init__(self, *, track17: Track17Tracker | None = None) -> None:
        self._track17 = track17

    async def fetch(self, tracking_id: str) -> TrackingResult:
        normalized = tracking_id.upper().strip()
        if self._track17 is None:
            return TrackingResult(
                tracking_number=normalized,
                found=False,
                carrier_name=self.CARRIER_NAME,
                carrier_code=self.CARRIER_CODE,
                error="track17 not configured",
            )

        result = await self._track17.fetch(normalized)
        result.carrier_name = self.CARRIER_NAME
        result.carrier_code = self.CARRIER_CODE
        return result
