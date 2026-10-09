"""Authentication for the web dashboard and the JSON API.

- Browser: the bot sends a one-time link (/web). Opening it shows a "Continue"
  button that POSTs the token, so link previews and prefetchers that follow the
  link cannot burn it. A successful login starts a server-side session; the
  cookie is HttpOnly, SameSite=Lax and Secure when WEB_PUBLIC_URL is https.
- Every state-changing form carries the session's CSRF token.
- API: ``Authorization: Bearer ptb_…`` personal tokens created in Settings.
- Authorisation is re-checked on every request, so revoking a user in Telegram
  locks them out of the dashboard immediately.
"""

from __future__ import annotations

import hmac
import logging
from collections.abc import Awaitable, Callable
from datetime import timedelta
from types import SimpleNamespace
from typing import Any

from aiohttp import web

from parcel_tracker.bot.auth_gate import is_authorized
from parcel_tracker.db.web_repository import WebRepository, WebSession
from parcel_tracker.web.keys import API_USER, BOT_DATA, SESSION

logger = logging.getLogger(__name__)

SESSION_COOKIE = "ptb_session"
Handler = Callable[[web.Request], Awaitable[web.StreamResponse]]

# Paths reachable without a browser session.
_PUBLIC_PREFIXES = ("/static/", "/t/", "/api/", "/login", "/healthz", "/favicon")


def bot_data(request: web.Request) -> dict[str, Any]:
    data: dict[str, Any] = request.app[BOT_DATA]
    return data


def web_repo(request: web.Request) -> WebRepository:
    repo: WebRepository = bot_data(request)["web_repo"]
    return repo


async def user_is_authorized(request: web.Request, user_id: int) -> bool:
    return await is_authorized(SimpleNamespace(bot_data=bot_data(request)), user_id)


def session(request: web.Request) -> WebSession:
    """The current session (only call from handlers behind the session check)."""
    current: WebSession = request[SESSION]
    return current


def user_id(request: web.Request) -> int:
    return session(request).user_id


def _cookie_secure(request: web.Request) -> bool:
    return str(bot_data(request)["config"].web_public_url).startswith("https://")


def set_session_cookie(request: web.Request, response: web.StreamResponse, value: str) -> None:
    days = int(bot_data(request)["config"].web_session_days)
    response.set_cookie(
        SESSION_COOKIE,
        value,
        max_age=int(timedelta(days=days).total_seconds()),
        httponly=True,
        samesite="Lax",
        secure=_cookie_secure(request),
        path="/",
    )


def clear_session_cookie(response: web.StreamResponse) -> None:
    response.del_cookie(SESSION_COOKIE, path="/")


@web.middleware
async def security_headers(request: web.Request, handler: Handler) -> web.StreamResponse:
    try:
        response = await handler(request)
    except web.HTTPException as exc:
        response = exc
        _apply_headers(request, response)
        raise
    _apply_headers(request, response)
    return response


def _apply_headers(request: web.Request, response: web.StreamResponse) -> None:
    headers = response.headers
    headers.setdefault(
        "Content-Security-Policy",
        "default-src 'self'; img-src 'self' data:; style-src 'self'; script-src 'self'; "
        "object-src 'none'; base-uri 'none'; form-action 'self'; frame-ancestors 'none'",
    )
    headers.setdefault("X-Content-Type-Options", "nosniff")
    headers.setdefault("X-Frame-Options", "DENY")
    # Login links and share links carry tokens in the URL: never leak them.
    headers.setdefault("Referrer-Policy", "no-referrer")
    headers.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
    if not request.path.startswith("/static/"):
        headers.setdefault("Cache-Control", "no-store")


@web.middleware
async def error_pages(request: web.Request, handler: Handler) -> web.StreamResponse:
    """Friendly HTML pages for 403/404 on browser routes (the API keeps JSON)."""
    try:
        return await handler(request)
    except web.HTTPException as exc:
        if exc.status not in (403, 404) or request.path.startswith(("/api/", "/static/")):  # noqa: PLR2004
            raise
        from parcel_tracker.web.views import page  # noqa: PLC0415

        return await page(
            request,
            "error.html",
            {
                "status": exc.status,
                "message": exc.text
                if exc.text and not exc.text.startswith(str(exc.status))
                else "",
            },
            public=request.path.startswith("/t/") or SESSION not in request,
            status=exc.status,
        )


@web.middleware
async def session_middleware(request: web.Request, handler: Handler) -> web.StreamResponse:
    """Attach the session; send anonymous browsers to /login; enforce CSRF on POST."""
    cookie = request.cookies.get(SESSION_COOKIE)
    current = await web_repo(request).get_session(cookie) if cookie else None
    if current is not None and not await user_is_authorized(request, current.user_id):
        await web_repo(request).delete_sessions_for_user(current.user_id)
        current = None
    if current is not None:
        request[SESSION] = current
    if request.path.startswith(_PUBLIC_PREFIXES) or request.path == "/logout":
        return await handler(request)
    if current is None:
        raise web.HTTPSeeOther("/login")
    if request.method == "POST":
        await check_csrf(request, current)
    return await handler(request)


async def check_csrf(request: web.Request, current: WebSession) -> None:
    form = await request.post()
    sent = form.get("csrf")
    if not isinstance(sent, str) or not hmac.compare_digest(sent, current.csrf_token):
        logger.info("rejected POST %s without a valid CSRF token", request.path)
        raise web.HTTPForbidden(text="Invalid or missing CSRF token. Reload the page and retry.")


@web.middleware
async def api_auth_middleware(request: web.Request, handler: Handler) -> web.StreamResponse:
    """Bearer-token authentication for /api/*; errors are JSON."""
    if not request.path.startswith("/api/"):
        return await handler(request)
    header = request.headers.get("Authorization", "")
    scheme, _, token = header.partition(" ")
    if scheme.lower() != "bearer" or not token:
        return _api_error(401, "missing bearer token")
    uid = await web_repo(request).user_for_api_token(token.strip())
    if uid is None or not await user_is_authorized(request, uid):
        return _api_error(401, "invalid token")
    request[API_USER] = uid
    try:
        return await handler(request)
    except web.HTTPException as exc:
        if exc.status >= 400:  # noqa: PLR2004
            return _api_error(exc.status, exc.reason)
        raise


def _api_error(status: int, message: str) -> web.Response:
    return web.json_response({"error": message}, status=status)


# --- login / logout --------------------------------------------------------------


async def login_page(request: web.Request) -> web.StreamResponse:
    from parcel_tracker.web.views import page  # noqa: PLC0415

    token = request.query.get("t", "")
    return await page(request, "login.html", {"token": token, "error": None}, public=True)


async def login_submit(request: web.Request) -> web.StreamResponse:
    from parcel_tracker.web.views import page  # noqa: PLC0415

    form = await request.post()
    token = form.get("t")
    uid = await web_repo(request).consume_login_token(token) if isinstance(token, str) else None
    if uid is None or not await user_is_authorized(request, uid):
        return await page(
            request, "login.html", {"token": "", "error": "expired"}, public=True, status=400
        )
    days = int(bot_data(request)["config"].web_session_days)
    session_id = await web_repo(request).create_session(uid, lifetime=timedelta(days=days))
    response = web.HTTPSeeOther("/")
    set_session_cookie(request, response, session_id)
    logger.info("web login for user %s", uid)
    raise response


async def logout(request: web.Request) -> web.StreamResponse:
    cookie = request.cookies.get(SESSION_COOKIE)
    current = request.get(SESSION)
    if request.method == "POST" and current is not None:
        await check_csrf(request, current)
    if cookie:
        await web_repo(request).delete_session(cookie)
    response = web.HTTPSeeOther("/login?bye=1")
    clear_session_cookie(response)
    raise response
