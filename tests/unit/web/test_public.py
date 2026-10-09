"""Public tracking page: carrier data only, never the seller's fields."""

from __future__ import annotations

from tests.unit.web.conftest import OWNER


async def test_public_page_shows_carrier_data_only(env) -> None:
    repo = env.bot_data["parcel_repo"]
    await repo.update_details("1Z999AA10123456784", user_id=OWNER, notes="VIP — gave discount")
    await repo.set_share_token("1Z999AA10123456784", user_id=OWNER, token="public-token-123")
    await env.bot_data["settings"].set_user(OWNER, "shop_name", "Bottega Aurora")
    resp = await env.client.get("/t/public-token-123")
    html = await resp.text()
    assert resp.status == 200
    assert "Out for delivery" in html
    assert "1Z999AA10123456784" in html
    assert "Bottega Aurora" in html
    for private in (
        "Ceramic mug",
        "#1042",
        "Ada Lovelace",
        "Milano",
        "VIP — gave discount",
        "gift",
    ):
        assert private not in html, private
    assert "noindex" in html


async def test_unknown_or_revoked_link(env) -> None:
    resp = await env.client.get("/t/does-not-exist")
    assert resp.status == 404
    assert "revoked" in await resp.text()
    assert (await env.client.get("/t/x/map.png")).status == 404


async def test_public_page_language_follows_browser(env) -> None:
    await env.bot_data["parcel_repo"].set_share_token(
        "RR123456785IT", user_id=OWNER, token="tok-it-000000000000"
    )
    resp = await env.client.get(
        "/t/tok-it-000000000000", headers={"Accept-Language": "it-IT,it;q=0.9"}
    )
    assert 'lang="it"' in await resp.text()
