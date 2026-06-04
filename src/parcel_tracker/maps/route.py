"""Build a geographic route (waypoints) from a parcel's tracking-event chain."""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from parcel_tracker.db.models import TrackingEvent


class _GeocoderLike(Protocol):
    def geocode(self, location: str | None) -> tuple[float, float] | None: ...


def build_route_waypoints(
    events: list[TrackingEvent], geocoder: _GeocoderLike
) -> list[tuple[float, float]]:
    """Geocode each event location in order; drop ungeocodable ones and collapse
    consecutive duplicate coordinates. Returns chronological waypoints."""
    waypoints: list[tuple[float, float]] = []
    for ev in events:
        coord = geocoder.geocode(ev.location) if ev.location else None
        if coord is None:
            continue
        if waypoints and waypoints[-1] == coord:
            continue
        waypoints.append(coord)
    return waypoints
