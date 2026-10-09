"""Login flow, sessions, CSRF and authorisation."""

from __future__ import annotations

from tests.unit.web.conftest import OWNER, STRANGER, login


async def test_anonymous_is_sent_to_login(env) -> None:
    resp = await env.client.get("/", allow_redirects=False)
    assert resp.status == 303
    assert resp.headers["Location"] == "/login"
    page = await env.client.get("/login")
    assert "/web" in await page.text()


async def test_get_with_token_does_not_consume_it(env) -> None:
    # Link previews and prefetchers only GET: the token must survive them.
    token = await env.bot_data["web_repo"].create_login_token(OWNER)
    page = await env.client.get(f"/login?t={token}")
    assert page.status == 200
    assert token in await page.text()
    resp = await env.client.post("/login", data={"t": token}, allow_redirects=False)
    assert resp.status == 303
    cookie = resp.cookies["ptb_session"]
    assert cookie["httponly"]
    assert cookie["samesite"] == "Lax"


async def test_login_token_is_single_use(env) -> None:
    token = await env.bot_data["web_repo"].create_login_token(OWNER)
    first = await env.client.post("/login", data={"t": token}, allow_redirects=False)
    assert first.status == 303
    env.client.session.cookie_jar.clear()
    second = await env.client.post("/login", data={"t": token}, allow_redirects=False)
    assert second.status == 400
    assert "expired" in (await second.text()).lower()


async def test_unauthorised_user_cannot_sign_in(env) -> None:
    token = await env.bot_data["web_repo"].create_login_token(STRANGER)
    resp = await env.client.post("/login", data={"t": token}, allow_redirects=False)
    assert resp.status == 400


async def test_revoked_user_is_locked_out(env) -> None:
    await env.bot_data["user_repo"].add_user(user_id=5, added_by=OWNER)
    await login(env, user_id=5)
    assert (await env.client.get("/", allow_redirects=False)).status == 200
    await env.bot_data["user_repo"].remove_user(5)
    resp = await env.client.get("/", allow_redirects=False)
    assert resp.status == 303


async def test_post_without_csrf_is_rejected(env) -> None:
    await login(env)
    resp = await env.client.post("/settings", data={"shop_name": "Evil"})
    assert resp.status == 403
    assert await env.bot_data["settings"].shop_name(OWNER) is None


async def test_logout(env) -> None:
    csrf = await login(env)
    resp = await env.client.post("/logout", data={"csrf": csrf}, allow_redirects=False)
    assert resp.status == 303
    assert (await env.client.get("/", allow_redirects=False)).status == 303


async def test_logout_everywhere(env) -> None:
    csrf = await login(env)
    await env.client.post("/settings/logout-all", data={"csrf": csrf}, allow_redirects=False)
    assert (await env.client.get("/", allow_redirects=False)).status == 303


async def test_security_headers(env) -> None:
    resp = await env.client.get("/login")
    assert "default-src 'self'" in resp.headers["Content-Security-Policy"]
    assert resp.headers["Referrer-Policy"] == "no-referrer"
    assert resp.headers["X-Frame-Options"] == "DENY"
    assert resp.headers["Cache-Control"] == "no-store"


async def test_static_and_health(env) -> None:
    assert (await env.client.get("/healthz")).status == 200
    css = await env.client.get("/static/app.css")
    assert css.status == 200
    assert "Cache-Control" not in css.headers or css.headers["Cache-Control"] != "no-store"


async def test_html_404_page(env) -> None:
    await login(env)
    resp = await env.client.get("/shipments/999999")
    assert resp.status == 404
    assert "Not found" in await resp.text()
