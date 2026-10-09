"""aiohttp application factory and an embeddable server.

The server shares the bot's event loop: it is started from the Telegram
application's post_init hook and stopped on shutdown, so there is one process,
one database and one set of trackers.
"""

from __future__ import annotations

import logging
from collections import OrderedDict
from pathlib import Path
from typing import Any

from aiohttp import web

from parcel_tracker.web import api, auth, public, views
from parcel_tracker.web.keys import BOT_DATA, JINJA, MAP_CACHE
from parcel_tracker.web.render import build_environment

logger = logging.getLogger(__name__)

STATIC = Path(__file__).parent / "static"
MAX_UPLOAD_BYTES = 2 * 1024 * 1024


async def healthz(_request: web.Request) -> web.StreamResponse:
    return web.Response(text="ok")


async def favicon(_request: web.Request) -> web.StreamResponse:
    raise web.HTTPMovedPermanently("/static/favicon.svg")


def create_app(bot_data: dict[str, Any]) -> web.Application:
    app = web.Application(
        middlewares=[
            auth.security_headers,
            auth.api_auth_middleware,
            auth.error_pages,
            auth.session_middleware,
        ],
        client_max_size=MAX_UPLOAD_BYTES,
    )
    app[BOT_DATA] = bot_data
    app[JINJA] = build_environment()
    app[MAP_CACHE] = OrderedDict()
    app.add_routes(
        [
            web.get("/healthz", healthz),
            web.get("/favicon.ico", favicon),
            web.get("/login", auth.login_page),
            web.post("/login", auth.login_submit),
            web.post("/logout", auth.logout),
            web.get("/", views.dashboard),
            web.get("/shipments", views.shipments),
            web.get("/shipments/new", views.new_shipment),
            web.post("/shipments", views.create_shipment),
            web.get("/shipments/{parcel_id:\\d+}", views.shipment_detail),
            web.post("/shipments/{parcel_id:\\d+}", views.update_shipment),
            web.post("/shipments/{parcel_id:\\d+}/refresh", views.refresh_shipment),
            web.post("/shipments/{parcel_id:\\d+}/archive", views.archive_shipment),
            web.post("/shipments/{parcel_id:\\d+}/restore", views.restore_shipment),
            web.post("/shipments/{parcel_id:\\d+}/delete", views.delete_shipment),
            web.post("/shipments/{parcel_id:\\d+}/share", views.share_shipment),
            web.post("/shipments/{parcel_id:\\d+}/unshare", views.unshare_shipment),
            web.get("/shipments/{parcel_id:\\d+}/map.png", views.shipment_map),
            web.get("/export.csv", views.export),
            web.get("/import", views.import_page),
            web.post("/import", views.import_submit),
            web.get("/import/template.csv", views.import_template),
            web.get("/settings", views.settings_view),
            web.post("/settings", views.settings_save),
            web.post("/settings/tokens", views.token_create),
            web.post("/settings/tokens/{token_id:\\d+}/revoke", views.token_revoke),
            web.post("/settings/logout-all", views.logout_everywhere),
            web.post("/settings/erase", views.erase_account),
            web.get("/t/{token}", public.tracking_page),
            web.get("/t/{token}/map.png", public.tracking_map),
            web.get("/api/v1/shipments", api.list_shipments),
            web.post("/api/v1/shipments", api.create_shipment),
            web.get("/api/v1/shipments/{tracking_number}", api.get_shipment),
            web.patch("/api/v1/shipments/{tracking_number}", api.update_shipment),
            web.delete("/api/v1/shipments/{tracking_number}", api.delete_shipment),
            web.get("/api/v1/stats", api.stats),
            web.static("/static", STATIC, append_version=True),
        ]
    )
    return app


class WebServer:
    """Start/stop the dashboard inside an already running event loop."""

    def __init__(self, bot_data: dict[str, Any], *, host: str, port: int) -> None:
        self._app = create_app(bot_data)
        self._host = host
        self._port = port
        self._runner: web.AppRunner | None = None

    @property
    def app(self) -> web.Application:
        return self._app

    async def start(self) -> None:
        self._runner = web.AppRunner(self._app, access_log=None)
        await self._runner.setup()
        site = web.TCPSite(self._runner, self._host, self._port)
        await site.start()
        logger.info("web dashboard listening on http://%s:%d", self._host, self._port)

    async def stop(self) -> None:
        if self._runner is not None:
            await self._runner.cleanup()
            self._runner = None
