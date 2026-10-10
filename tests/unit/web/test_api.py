"""JSON API v1."""

from __future__ import annotations

from tests.unit.web.conftest import OWNER


async def _headers(env, user_id: int = OWNER) -> dict[str, str]:
    token = await env.bot_data["web_repo"].create_api_token(user_id, "test")
    return {"Authorization": f"Bearer {token}"}


async def test_requires_a_valid_token(env) -> None:
    assert (await env.client.get("/api/v1/shipments")).status == 401
    bad = await env.client.get("/api/v1/shipments", headers={"Authorization": "Bearer ptb_nope"})
    assert bad.status == 401
    assert (await bad.json()) == {"error": "invalid token"}


async def test_list_and_filter(env) -> None:
    h = await _headers(env)
    data = await (await env.client.get("/api/v1/shipments", headers=h)).json()
    assert data["total"] == 5
    codes = {s["tracking_number"] for s in data["shipments"]}
    assert "RR123456785IT" in codes
    attention = await (await env.client.get("/api/v1/shipments?view=attention", headers=h)).json()
    assert {s["tracking_number"] for s in attention["shipments"]} == {
        "LX987654321CN",
        "JD014600006281234567",
    }
    page = await (await env.client.get("/api/v1/shipments?limit=2&offset=1", headers=h)).json()
    assert len(page["shipments"]) == 2
    assert (await env.client.get("/api/v1/shipments?view=nope", headers=h)).status == 400


async def test_create_get_patch_delete(env) -> None:
    h = await _headers(env)
    created = await env.client.post(
        "/api/v1/shipments",
        json={
            "tracking_number": "zz-1234-5678",
            "order_ref": "W-1",
            "recipient": "Ada",
            "tags": ["VIP"],
        },
        headers=h,
    )
    assert created.status == 201
    body = await created.json()
    assert body["tracking_number"] == "ZZ12345678"
    assert body["tags"] == ["vip"]
    assert body["status"] == "NotFound"
    assert (
        await env.client.post(
            "/api/v1/shipments", json={"tracking_number": "ZZ12345678"}, headers=h
        )
    ).status == 409
    assert (
        await env.client.post("/api/v1/shipments", json={"tracking_number": "?"}, headers=h)
    ).status == 422
    assert (await env.client.post("/api/v1/shipments", data="nope", headers=h)).status == 400

    got = await (await env.client.get("/api/v1/shipments/zz12345678?events=1", headers=h)).json()
    assert got["order_ref"] == "W-1"
    assert got["events"] == []

    patched = await env.client.patch(
        "/api/v1/shipments/ZZ12345678", json={"notes": "fragile", "recipient": None}, headers=h
    )
    assert (await patched.json())["notes"] == "fragile"
    assert (await patched.json())["recipient"] is None

    assert (await env.client.delete("/api/v1/shipments/ZZ12345678", headers=h)).status == 204
    archived = await (await env.client.get("/api/v1/shipments/ZZ12345678", headers=h)).json()
    assert archived["active"] is False
    assert (
        await env.client.delete("/api/v1/shipments/ZZ12345678?purge=1", headers=h)
    ).status == 204
    assert (await env.client.get("/api/v1/shipments/ZZ12345678", headers=h)).status == 404


async def test_tokens_are_scoped_to_their_owner(env) -> None:
    await env.bot_data["user_repo"].add_user(user_id=5, added_by=OWNER)
    h = await _headers(env, user_id=5)
    data = await (await env.client.get("/api/v1/shipments", headers=h)).json()
    assert data["total"] == 0
    assert (await env.client.get("/api/v1/shipments/RR123456785IT", headers=h)).status == 404


async def test_revoked_user_token_stops_working(env) -> None:
    await env.bot_data["user_repo"].add_user(user_id=5, added_by=OWNER)
    h = await _headers(env, user_id=5)
    assert (await env.client.get("/api/v1/stats", headers=h)).status == 200
    await env.bot_data["user_repo"].remove_user(5)
    assert (await env.client.get("/api/v1/stats", headers=h)).status == 401


async def test_stats(env) -> None:
    h = await _headers(env)
    stats = await (await env.client.get("/api/v1/stats", headers=h)).json()
    assert stats["total"] == 5
    assert stats["active"] == 4
    assert stats["stalled"] == 1
    assert stats["median_delivery_days"] == 3.5
    assert {c["carrier"] for c in stats["carriers"]} >= {"UPS", "DHL Paket"}
