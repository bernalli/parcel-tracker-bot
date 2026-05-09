"""Abstract tracker contract: AbstractTracker, TrackingResult."""

from __future__ import annotations

import re
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import ClassVar

from parcel_tracker.db.models import ShipmentStatus, TrackingEvent


@dataclass(slots=True)
class TrackingResult:
    """Result returned by a tracker for a single tracking ID lookup."""

    tracking_number: str
    found: bool
    status: ShipmentStatus = ShipmentStatus.NOT_FOUND
    carrier_code: str | None = None
    carrier_name: str | None = None
    all_carriers: list[str] = field(default_factory=list)
    origin: str | None = None
    destination: str | None = None
    last_event: str | None = None
    last_event_time: str | None = None
    events: list[TrackingEvent] = field(default_factory=list)
    error: str | None = None
    carrier_handoff: bool = False


class AbstractTracker(ABC):
    """
    Base class for all tracker plugins.

    Subclasses MUST set the class attributes (name, priority, country_codes,
    tracking_id_patterns, url_patterns) and implement `fetch`.
    """

    name: ClassVar[str] = ""
    priority: ClassVar[int] = 0
    country_codes: ClassVar[list[str]] = []
    tracking_id_patterns: ClassVar[list[re.Pattern[str]]] = []
    url_patterns: ClassVar[list[re.Pattern[str]]] = []

    def detect(self, tracking_id_or_url: str) -> bool:
        """Return True if this tracker can handle the given ID or URL."""
        for pattern in self.tracking_id_patterns:
            if pattern.match(tracking_id_or_url):
                return True
        for pattern in self.url_patterns:
            if pattern.search(tracking_id_or_url):
                return True
        return False

    @abstractmethod
    async def fetch(self, tracking_id: str) -> TrackingResult:
        """Look up the given tracking ID. Must be async."""
        raise NotImplementedError
