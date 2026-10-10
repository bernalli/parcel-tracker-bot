"""Route maps on the dashboard and on public tracking pages."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

from parcel_tracker.db.models import Parcel, TrackingEvent
from tests.unit.web.conftest import OWNER, login

PNG = b"\x89PNG fake"
CODE = "1Z999AA10123456784"


class StubGeocoder:
    def __init__(self, coord: tuple[float, float] | None = (44.49, 11.34)) -> None:
        self.coord = coord
        self.calls = 0

    def geocode(self, location: str | None) -> tuple[float, float] | None:
        self.calls += 1
        return self.coord


class StubRenderer:
    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail
        self.calls: list[tuple[list[tuple[float, float]], str]] = []

    def render_route(self, waypoints: list[tuple[float, float]], *, mode: str) -> bytes:
        self.calls.append((waypoints, mode))
        if self.fail:
            raise RuntimeError("tile server down")
        return PNG


def _enable_maps(
    env: SimpleNamespace, geocoder: StubGeocoder | None = None, renderer: StubRenderer | None = None
) -> tuple[StubGeocoder, StubRenderer]:
    geocoder = geocoder or StubGeocoder()
    renderer = renderer or StubRenderer()
    env.bot_data["geocoder"] = geocoder
    env.bot_data["map_renderer"] = renderer
    return geocoder, renderer


async def _id(env: SimpleNamespace, code: str = CODE) -> int:
    parcel = await env.bot_data["parcel_repo"].get_for_user(code, user_id=OWNER)
    assert parcel is not None and parcel.id is not None
    return parcel.id


async def test_map_is_rendered_once_and_cached(env) -> None:
    _, renderer = _enable_maps(env)
    await login(env)
    pid = await _id(env)
    detail = await env.client.get(f"/shipments/{pid}")
    assert f'src="/shipments/{pid}/map.png"' in await detail.text()
    for _ in range(2):
        resp = await env.client.get(f"/shipments/{pid}/map.png")
        assert resp.status == 200
        assert resp.content_type == "image/png"
        assert resp.headers["Cache-Control"].startswith("private")
        assert await resp.read() == PNG
    assert len(renderer.calls) == 1
    assert renderer.calls[0][0] == [(44.49, 11.34)]


async def test_map_is_redrawn_after_the_parcel_changes(env) -> None:
    _, renderer = _enable_maps(env)
    await login(env)
    pid = await _id(env)
    assert (await env.client.get(f"/shipments/{pid}/map.png")).status == 200
    later = datetime.now(UTC) + timedelta(minutes=5)
    await env.bot_data["parcel_repo"].touch_change(CODE, later, user_id=OWNER)
    assert (await env.client.get(f"/shipments/{pid}/map.png")).status == 200
    assert len(renderer.calls) == 2


async def test_no_position_gives_404_without_rendering(env) -> None:
    geocoder, renderer = _enable_maps(env, geocoder=StubGeocoder(coord=None))
    await login(env)
    pid = await _id(env)
    for _ in range(2):
        assert (await env.client.get(f"/shipments/{pid}/map.png")).status == 404
    assert renderer.calls == []
    calls_after_first = geocoder.calls
    assert calls_after_first > 0
    # The empty result is cached too: no second geocoding pass.
    assert (await env.client.get(f"/shipments/{pid}/map.png")).status == 404
    assert geocoder.calls == calls_after_first


async def test_render_failure_is_a_404_not_an_error(env) -> None:
    _enable_maps(env, renderer=StubRenderer(fail=True))
    await login(env)
    pid = await _id(env)
    assert (await env.client.get(f"/shipments/{pid}/map.png")).status == 404


async def test_map_is_hidden_and_404_when_maps_are_off(env) -> None:
    await login(env)
    pid = await _id(env)
    assert "map.png" not in await (await env.client.get(f"/shipments/{pid}")).text()
    assert (await env.client.get(f"/shipments/{pid}/map.png")).status == 404


async def test_another_users_map_is_not_served(env) -> None:
    _, renderer = _enable_maps(env)
    repo = env.bot_data["parcel_repo"]
    other = await repo.create(Parcel(tracking_number="OTHER12345", user_id=2))
    assert other is not None
    await repo.add_events_dedup(
        "OTHER12345",
        [TrackingEvent(time="2026-01-02T10:00:00Z", description="Hub", location="Paris")],
        user_id=2,
    )
    await login(env)
    assert (await env.client.get(f"/shipments/{other.id}/map.png")).status == 404
    assert renderer.calls == []


async def test_public_map_shares_the_cache(env) -> None:
    _, renderer = _enable_maps(env)
    await env.bot_data["parcel_repo"].set_share_token(
        CODE, user_id=OWNER, token="map-token-0000000"
    )
    page = await env.client.get("/t/map-token-0000000")
    assert 'src="/t/map-token-0000000/map.png"' in await page.text()
    resp = await env.client.get("/t/map-token-0000000/map.png")
    assert resp.status == 200
    assert await resp.read() == PNG
    await login(env)
    assert (await env.client.get(f"/shipments/{await _id(env)}/map.png")).status == 200
    assert len(renderer.calls) == 1
