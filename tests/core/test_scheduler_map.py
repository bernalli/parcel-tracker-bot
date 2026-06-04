# tests/core/test_scheduler_map.py
from __future__ import annotations

import pytest

from parcel_tracker.core import scheduler
from parcel_tracker.db.models import TrackingEvent


class _Geo:
    def geocode(self, loc):
        return {"Milano, IT": (45.46, 9.19), "Roma, IT": (41.9, 12.5)}.get(loc or "")


class _Renderer:
    def __init__(self):
        self.calls = []

    def render_route(self, waypoints, *, mode):
        self.calls.append((waypoints, mode))
        return b"PNG"


@pytest.mark.asyncio
async def test_maybe_render_map_builds_route_from_history(monkeypatch) -> None:
    events = [
        TrackingEvent(time="t1", description="a", location="Milano, IT"),
        TrackingEvent(time="t2", description="b", location="Roma, IT"),
    ]
    renderer = _Renderer()
    png = await scheduler._maybe_render_map(
        geocoder=_Geo(),
        map_renderer=renderer,
        history=events,
        new_events=events,
    )
    assert png == b"PNG"
    assert renderer.calls[0][0] == [(45.46, 9.19), (41.9, 12.5)]


@pytest.mark.asyncio
async def test_maybe_render_map_none_when_no_geocodable() -> None:
    events = [TrackingEvent(time="t", description="x", location="Nowhere")]
    png = await scheduler._maybe_render_map(
        geocoder=_Geo(), map_renderer=_Renderer(), history=events, new_events=events
    )
    assert png is None
