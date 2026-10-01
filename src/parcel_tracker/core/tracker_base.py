"""Abstract tracker contract: AbstractTracker, TrackingResult."""

from __future__ import annotations

import re
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import ClassVar

import httpx

from parcel_tracker.db.models import ShipmentStatus, TrackingEvent


class FetchError(Enum):
    """Why a lookup returned ``found=False``.

    The scheduler treats them differently: NOT_FOUND and PERMANENT fall through to
    the next tracker; TRANSIENT and RATE_LIMITED end this cycle's lookup (the HTTP
    layer already retried) so a momentary outage does not burn fallback quota.
    """

    NOT_FOUND = "not_found"
    TRANSIENT = "transient"
    RATE_LIMITED = "rate_limited"
    PERMANENT = "permanent"


_TRANSIENT_EXCEPTIONS = (httpx.TimeoutException, httpx.NetworkError, httpx.RemoteProtocolError)


def classify_status(status_code: int) -> FetchError:
    """Map a non-200 HTTP status to a FetchError."""
    if status_code == 429:  # noqa: PLR2004
        return FetchError.RATE_LIMITED
    if status_code == 408 or status_code >= 500:  # noqa: PLR2004
        return FetchError.TRANSIENT
    if status_code in (404, 410):  # noqa: PLR2004
        return FetchError.NOT_FOUND
    return FetchError.PERMANENT


def classify_exception(exc: BaseException) -> FetchError:
    """Map an exception raised while fetching to a FetchError."""
    if isinstance(exc, _TRANSIENT_EXCEPTIONS):
        return FetchError.TRANSIENT
    return FetchError.PERMANENT


@dataclass(slots=True)
class TrackingResult:
    """Result returned by a tracker for a single tracking ID lookup."""

    tracking_number: str
    found: bool
    status: ShipmentStatus = ShipmentStatus.NOT_FOUND
    carrier_code: str | None = None
    carrier_name: str | None = None
    all_carriers: list[str] = field(default_factory=list)
    last_event: str | None = None
    last_event_time: str | None = None
    last_location: str | None = None
    events: list[TrackingEvent] = field(default_factory=list)
    error: str | None = None
    carrier_handoff: bool = False
    error_kind: FetchError = FetchError.NOT_FOUND


def last_location_from(events: list[TrackingEvent]) -> str | None:
    """First non-empty event location in list order (events are newest-first)."""
    for ev in events:
        if ev.location:
            return ev.location
    return None


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
