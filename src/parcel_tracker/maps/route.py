"""Build a geographic route (waypoints) from a parcel's tracking-event chain."""

from __future__ import annotations

import re
from datetime import datetime
from typing import TYPE_CHECKING, Protocol

from parcel_tracker.maps.location_hint import extract_location_hint

if TYPE_CHECKING:
    from parcel_tracker.db.models import TrackingEvent


class _GeocoderLike(Protocol):
    def geocode(self, location: str | None) -> tuple[float, float] | None: ...


_SLASH_RE = re.compile(r"^(\d{1,2})/(\d{1,2})/(\d{4})(?:[ T](\d{1,2}):(\d{2}))?")
_DOT_FORMATS = ("%d.%m.%Y %H.%M", "%d.%m.%Y %H:%M", "%d.%m.%Y")
_MONTHS_MAX = 12


def _parse_event_dt(raw: str | None) -> datetime | None:
    """Parse a carrier-provided time string to a naive datetime for ordering.

    Carrier `time` is free text in many formats (ISO from 17track, 'dd.mm.YYYY
    HH.MM' from BRT, slash dates from web scrapers). Returns None when no known
    format matches, so callers can fall back to insertion order."""
    if not raw:
        return None
    text = raw.strip()
    try:
        dt = datetime.fromisoformat(text.replace("Z", "+00:00"))
        return dt.replace(tzinfo=None) if dt.tzinfo is not None else dt
    except ValueError:
        pass
    for fmt in _DOT_FORMATS:
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            pass
    m = _SLASH_RE.match(text)
    if m:
        a, b, year = int(m.group(1)), int(m.group(2)), int(m.group(3))
        hh, mm = int(m.group(4) or 0), int(m.group(5) or 0)
        # Day-first (most couriers) unless the second field can't be a month.
        if b > _MONTHS_MAX and a <= _MONTHS_MAX:
            day, month = b, a
        else:
            day, month = a, b
        try:
            return datetime(year, month, day, hh, mm)
        except ValueError:
            return None
    return None


def order_events(events: list[TrackingEvent]) -> list[TrackingEvent]:
    """Return events oldest-first by parsed time. Events with an unparseable
    time keep their relative input order (stable sort) and sort first."""
    return sorted(events, key=lambda e: _parse_event_dt(e.time) or datetime.min)


def build_route_waypoints(
    events: list[TrackingEvent], geocoder: _GeocoderLike
) -> list[tuple[float, float]]:
    """Geocode each event location in chronological order; drop ungeocodable ones
    and collapse consecutive duplicate coordinates. Returns chronological waypoints."""
    waypoints: list[tuple[float, float]] = []
    for ev in order_events(events):
        loc = ev.location or extract_location_hint(ev.description)
        coord = geocoder.geocode(loc) if loc else None
        if coord is None:
            continue
        if waypoints and waypoints[-1] == coord:
            continue
        waypoints.append(coord)
    return waypoints
