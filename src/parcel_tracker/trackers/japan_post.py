"""Japan Post tracker (Tier D — detection + Track17 delega)."""

from __future__ import annotations

import re
from typing import ClassVar

from parcel_tracker.trackers._track17_backed import Track17BackedTracker


class JapanPostTracker(Track17BackedTracker):
    """Japan Post — UPU JP suffix, detection-only with Track17 delega."""

    name: ClassVar[str] = "japan_post"
    priority: ClassVar[int] = 31
    country_codes: ClassVar[list[str]] = ["JP"]
    tracking_id_patterns: ClassVar[list[re.Pattern[str]]] = [
        re.compile(r"^[A-Z]{2}\d{9}JP$"),
    ]
    url_patterns: ClassVar[list[re.Pattern[str]]] = []

    CARRIER_NAME: ClassVar[str] = "Japan Post"
    CARRIER_CODE: ClassVar[str] = "jp_post"
