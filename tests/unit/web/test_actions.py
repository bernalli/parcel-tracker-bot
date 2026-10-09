"""Shipment actions from the dashboard, scoped to their owner."""

from __future__ import annotations

import io

from aiohttp import FormData

from parcel_tracker.db.models import Parcel
from tests.unit.web.conftest import OWNER, login


async def _id(env, code: str, user_id: int = OWNER) -> int:
    parcel = await env.bot_data["parcel_repo"].get_for_user(code, user_id=user_id)
    assert parcel is not None and parcel.id is not None
    return parcel.id


async def test_add_single_shipment(env) -> None:
    csrf = await login(env)
    resp = await env.client.post(
        "/shipments",
        data={
            "csrf": csrf,
            "tracking_number": "ab 1234 5678 cd",
            "name": "Vase",
            "order_ref": "#7",
            "tags": "Gift, vip",
        },
        allow_redirects=False,
    )
    assert resp.status == 303
    parcel = await env.bot_data["parcel_repo"].get_for_user("AB12345678CD", user_id=OWNER)
    assert parcel is not None
    assert (parcel.name, parcel.order_ref, parcel.tags) == ("Vase", "#7", ["gift", "vip"])
    assert resp.headers["Location"] == f"/shipments/{parcel.id}?msg=added"


async def test_add_rejects_invalid_and_duplicate(env) -> None:
    csrf = await login(env)
    bad = await env.client.post("/shipments", data={"csrf": csrf, "tracking_number": "??"})
    assert bad.status == 400
    dup = await env.client.post(
        "/shipments", data={"csrf": csrf, "tracking_number": "RR123456785IT"}
    )
    assert dup.status == 400
    assert "already track" in await dup.text()


async def test_bulk_add(env) -> None:
    csrf = await login(env)
    resp = await env.client.post(
        "/shipments",
        data={"csrf": csrf, "codes": "ZZ11111111 first\n\nZZ22222222\nRR123456785IT\n??"},
        allow_redirects=False,
    )
    assert resp.status == 303
    assert "msg=bulk&n=2&m=2" in resp.headers["Location"]


async def test_edit_details(env) -> None:
    csrf = await login(env)
    pid = await _id(env, "RR123456785IT")
    await env.client.post(
        f"/shipments/{pid}",
        data={
            "csrf": csrf,
            "name": "Tote",
            "recipient": "Grace",
            "notes": "Ring twice",
            "tags": "vip",
        },
    )
    parcel = await env.bot_data["parcel_repo"].get_for_user("RR123456785IT", user_id=OWNER)
    assert (parcel.name, parcel.recipient, parcel.notes, parcel.tags, parcel.order_ref) == (
        "Tote",
        "Grace",
        "Ring twice",
        ["vip"],
        None,
    )


async def test_archive_restore_delete(env) -> None:
    csrf = await login(env)
    repo = env.bot_data["parcel_repo"]
    pid = await _id(env, "RR123456785IT")
    await env.client.post(f"/shipments/{pid}/archive", data={"csrf": csrf})
    assert not (await repo.get_for_user("RR123456785IT", user_id=OWNER)).is_active
    await env.client.post(f"/shipments/{pid}/restore", data={"csrf": csrf})
    assert (await repo.get_for_user("RR123456785IT", user_id=OWNER)).is_active
    await env.client.post(f"/shipments/{pid}/delete", data={"csrf": csrf})
    assert await repo.get_for_user("RR123456785IT", user_id=OWNER) is None


async def test_share_and_unshare(env) -> None:
    csrf = await login(env)
    repo = env.bot_data["parcel_repo"]
    pid = await _id(env, "RR123456785IT")
    await env.client.post(f"/shipments/{pid}/share", data={"csrf": csrf})
    token = (await repo.get_for_user("RR123456785IT", user_id=OWNER)).share_token
    assert token and len(token) >= 20
    html = await (await env.client.get(f"/shipments/{pid}")).text()
    assert f"http://testserver/t/{token}" in html
    await env.client.post(f"/shipments/{pid}/unshare", data={"csrf": csrf})
    assert (await repo.get_for_user("RR123456785IT", user_id=OWNER)).share_token is None


async def test_other_users_shipments_are_invisible(env) -> None:
    repo = env.bot_data["parcel_repo"]
    other = await repo.create(Parcel(tracking_number="OTHER12345", user_id=2, name="Not yours"))
    csrf = await login(env)
    assert (await env.client.get(f"/shipments/{other.id}")).status == 404
    resp = await env.client.post(f"/shipments/{other.id}/delete", data={"csrf": csrf})
    assert resp.status == 404
    assert await repo.get_for_user("OTHER12345", user_id=2) is not None
    listing = await (await env.client.get("/shipments?view=all")).text()
    assert "Not yours" not in listing


async def test_refresh_without_tracker_reports_failure(env) -> None:
    csrf = await login(env)
    env.bot_data.update(health=None, notifier=None, rate_limiter=None)
    pid = await _id(env, "RR123456785IT")
    resp = await env.client.post(
        f"/shipments/{pid}/refresh", data={"csrf": csrf}, allow_redirects=False
    )
    assert resp.status == 303
    assert "msg=refresh_failed" in resp.headers["Location"]
    again = await env.client.post(
        f"/shipments/{pid}/refresh", data={"csrf": csrf}, allow_redirects=False
    )
    assert "msg=wait" in again.headers["Location"]


async def test_export_and_import(env) -> None:
    csrf = await login(env)
    export = await env.client.get("/export.csv")
    body = (await export.read()).decode("utf-8-sig")
    assert export.headers["Content-Type"].startswith("text/csv")
    assert body.splitlines()[0].startswith("tracking_number,name,order_ref")
    assert "Ceramic mug" in body
    form = FormData()
    form.add_field("csrf", csrf)
    form.add_field(
        "file",
        io.BytesIO(b"codice;cliente\nZZ99999999;Mario Rossi\nRR123456785IT;dup\n"),
        filename="ordini.csv",
        content_type="text/csv",
    )
    resp = await env.client.post("/import", data=form)
    html = await resp.text()
    assert resp.status == 200
    assert "Import finished" in html
    imported = await env.bot_data["parcel_repo"].get_for_user("ZZ99999999", user_id=OWNER)
    assert imported is not None and imported.recipient == "Mario Rossi"
    template = await env.client.get("/import/template.csv")
    assert b"tracking_number" in await template.read()


async def test_settings_roundtrip(env) -> None:
    csrf = await login(env)
    await env.client.post(
        "/settings",
        data={
            "csrf": csrf,
            "seller_mode": "on",
            "shop_name": "  Bottega  Aurora ",
            "language": "it",
        },
    )
    assert await env.bot_data["settings"].seller_mode(OWNER)
    assert await env.bot_data["settings"].shop_name(OWNER) == "Bottega Aurora"
    assert await env.bot_data["user_repo"].get_language(OWNER) == "it"
    await env.client.post("/settings", data={"csrf": csrf, "shop_name": "", "language": "xx"})
    assert not await env.bot_data["settings"].seller_mode(OWNER)
    assert await env.bot_data["user_repo"].get_language(OWNER) == "it"


async def test_api_token_lifecycle_in_settings(env) -> None:
    csrf = await login(env)
    resp = await env.client.post("/settings/tokens", data={"csrf": csrf, "name": "Shop"})
    html = await resp.text()
    assert "ptb_" in html
    tokens = await env.bot_data["web_repo"].list_api_tokens(OWNER)
    assert [t.name for t in tokens] == ["Shop"]
    await env.client.post(f"/settings/tokens/{tokens[0].id}/revoke", data={"csrf": csrf})
    assert await env.bot_data["web_repo"].list_api_tokens(OWNER) == []


async def test_erase_requires_confirmation(env) -> None:
    csrf = await login(env)
    resp = await env.client.post("/settings/erase", data={"csrf": csrf}, allow_redirects=False)
    assert "confirm_needed" in resp.headers["Location"]
    assert await env.bot_data["parcel_repo"].list_all_for_user(user_id=OWNER)
    resp = await env.client.post(
        "/settings/erase", data={"csrf": csrf, "confirm": "on"}, allow_redirects=False
    )
    assert resp.headers["Location"].startswith("/login")
    assert await env.bot_data["parcel_repo"].list_all_for_user(user_id=OWNER) == []
    assert (await env.client.get("/", allow_redirects=False)).status == 303
