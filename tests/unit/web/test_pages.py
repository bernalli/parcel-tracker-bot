"""Every dashboard page renders for a signed-in user, in both languages."""

from __future__ import annotations

import pytest

from tests.unit.web.conftest import login


@pytest.mark.parametrize(
    "path",
    [
        "/",
        "/shipments",
        "/shipments?view=attention",
        "/shipments?view=delivered",
        "/shipments?view=archived",
        "/shipments?view=all&q=mug",
        "/shipments?view=all&carrier=UPS",
        "/shipments?view=all&tag=gift",
        "/shipments/new",
        "/import",
        "/settings",
    ],
)
async def test_pages_render(env, path: str) -> None:
    await login(env)
    resp = await env.client.get(path)
    assert resp.status == 200, path
    html = await resp.text()
    assert "<!doctype html>" in html
    assert "Content-Security-Policy" in resp.headers


async def test_dashboard_numbers(env) -> None:
    await login(env)
    html = await (await env.client.get("/")).text()
    assert "Ceramic mug" not in html or "Need attention" in html
    assert "Desk lamp" in html  # stalled for 12 days → needs attention
    assert "Notebook set" in html  # carrier exception → needs attention
    assert 'class="chart"' in html
    assert "Wool scarf" in html  # recently delivered


async def test_detail_page_shows_seller_fields(env) -> None:
    await login(env)
    parcel = await env.bot_data["parcel_repo"].get_for_user("1Z999AA10123456784", user_id=1)
    html = await (await env.client.get(f"/shipments/{parcel.id}")).text()
    assert "Ada Lovelace" in html
    assert "#1042" in html
    assert "Out for delivery" in html


async def test_italian_interface(env) -> None:
    await env.bot_data["user_repo"].set_language(1, "it")
    await login(env)
    html = await (await env.client.get("/")).text()
    assert 'lang="it"' in html
    assert "Spedizioni" in html
