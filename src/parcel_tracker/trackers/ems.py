"""EMS tracker (Tier D — detection + Track17 delega)."""

from __future__ import annotations

import re
from typing import ClassVar

from parcel_tracker.trackers._track17_backed import Track17BackedTracker


class EmsTracker(Track17BackedTracker):
    """EMS — E-prefix UPU pattern, last 2 letters indicate origin country."""

    name: ClassVar[str] = "ems"
    priority: ClassVar[int] = 33
    country_codes: ClassVar[list[str]] = ["GLOBAL"]
    tracking_id_patterns: ClassVar[list[re.Pattern[str]]] = [
        re.compile(r"^E[A-Z]\d{9}[A-Z]{2}$"),
    ]
    url_patterns: ClassVar[list[re.Pattern[str]]] = []

    CARRIER_NAME: ClassVar[str] = "EMS"
    CARRIER_CODE: ClassVar[str] = "ems"
