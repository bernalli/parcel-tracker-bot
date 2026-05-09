"""Singapore Post tracker (Tier D — detection + Track17 delega)."""

from __future__ import annotations

import re
from typing import ClassVar

from parcel_tracker.trackers._track17_backed import Track17BackedTracker


class SingaporePostTracker(Track17BackedTracker):
    """Singapore Post — UPU SG suffix, detection-only with Track17 delega."""

    name: ClassVar[str] = "singapore_post"
    priority: ClassVar[int] = 32
    country_codes: ClassVar[list[str]] = ["SG"]
    tracking_id_patterns: ClassVar[list[re.Pattern[str]]] = [
        re.compile(r"^[A-Z]{2}\d{9}SG$"),
    ]
    url_patterns: ClassVar[list[re.Pattern[str]]] = []

    CARRIER_NAME: ClassVar[str] = "Singapore Post"
    CARRIER_CODE: ClassVar[str] = "sg_post"
