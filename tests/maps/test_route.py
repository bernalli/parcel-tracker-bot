"""Tests for route waypoint building from tracking events."""

from __future__ import annotations

from parcel_tracker.db.models import TrackingEvent
from parcel_tracker.maps.route import build_route_waypoints


class _FakeGeocoder:
    def __init__(self, table: dict[str, tuple[float, float]]) -> None:
        self._t = table

    def geocode(self, location: str | None) -> tuple[float, float] | None:
        return self._t.get(location or "")


def test_builds_ordered_waypoints_skipping_ungeocodable() -> None:
    geo = _FakeGeocoder({"Milano, IT": (45.46, 9.19), "Roma, IT": (41.9, 12.5)})
    events = [
        TrackingEvent(time="t1", description="a", location="Milano, IT"),
        TrackingEvent(time="t2", description="b", location="Nowhere"),
        TrackingEvent(time="t3", description="c", location="Roma, IT"),
    ]
    assert build_route_waypoints(events, geo) == [(45.46, 9.19), (41.9, 12.5)]


def test_dedups_consecutive_identical_coords() -> None:
    geo = _FakeGeocoder({"Milano, IT": (45.46, 9.19), "Roma, IT": (41.9, 12.5)})
    events = [
        TrackingEvent(time="t1", description="a", location="Milano, IT"),
        TrackingEvent(time="t2", description="b", location="Milano, IT"),
        TrackingEvent(time="t3", description="c", location="Roma, IT"),
    ]
    assert build_route_waypoints(events, geo) == [(45.46, 9.19), (41.9, 12.5)]


def test_empty_when_nothing_geocodable() -> None:
    geo = _FakeGeocoder({})
    events = [TrackingEvent(time="t", description="x", location="Nowhere")]
    assert build_route_waypoints(events, geo) == []
