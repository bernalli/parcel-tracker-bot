"""Amazon Logistics tracker (Tier D — detection + Track17 delega)."""

from __future__ import annotations

import re
from typing import ClassVar

from parcel_tracker.trackers._track17_backed import Track17BackedTracker


class AmazonLogisticsTracker(Track17BackedTracker):
    """Amazon Logistics — TBA prefix tracking IDs, detection-only with Track17 delega."""

    name: ClassVar[str] = "amazon_logistics"
    priority: ClassVar[int] = 40
    country_codes: ClassVar[list[str]] = ["US", "GLOBAL"]
    tracking_id_patterns: ClassVar[list[re.Pattern[str]]] = [
        re.compile(r"^TBA\d{10,12}$"),
    ]
    url_patterns: ClassVar[list[re.Pattern[str]]] = [
        re.compile(r"amazon\.(com|co\.uk|de|fr|it|es).*orderId=", re.IGNORECASE),
    ]

    CARRIER_NAME: ClassVar[str] = "Amazon Logistics"
    CARRIER_CODE: ClassVar[str] = "amazon"
