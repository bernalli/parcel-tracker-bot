"""China Post tracker (Tier D — detection + Track17 delega)."""

from __future__ import annotations

import re
from typing import ClassVar

from parcel_tracker.trackers._track17_backed import Track17BackedTracker


class ChinaPostTracker(Track17BackedTracker):
    """China Post — UPU CN with leading-letter discriminator, detection-only with Track17 delega."""

    name: ClassVar[str] = "china_post"
    priority: ClassVar[int] = 35
    country_codes: ClassVar[list[str]] = ["CN"]
    tracking_id_patterns: ClassVar[list[re.Pattern[str]]] = [
        re.compile(r"^[LRCES][A-Z]\d{9}CN$"),
    ]
    url_patterns: ClassVar[list[re.Pattern[str]]] = []

    CARRIER_NAME: ClassVar[str] = "China Post"
    CARRIER_CODE: ClassVar[str] = "china_post"
