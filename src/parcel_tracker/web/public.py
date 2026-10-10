"""Public tracking page: what a seller shares with the customer.

Only carrier data is shown (status, events, route). The seller's own fields —
name, order reference, recipient, destination, notes, tags — never appear. The
URL holds a random token the seller can revoke at any time.
"""

from __future__ import annotations

from aiohttp import web

from parcel_tracker.db.models import Parcel
from parcel_tracker.db.repository import ParcelRepository
from parcel_tracker.db.settings_repository import SettingsRepository
from parcel_tracker.web.auth import bot_data
from parcel_tracker.web.views import map_response, page

_TOKEN_MAX = 64


async def _shared(request: web.Request) -> Parcel:
    token = request.match_info["token"]
    repo: ParcelRepository = bot_data(request)["parcel_repo"]
    parcel = await repo.get_by_share_token(token) if len(token) <= _TOKEN_MAX else None
    if parcel is None:
        raise web.HTTPNotFound(text="This tracking link does not exist or was revoked.")
    return parcel


async def tracking_page(request: web.Request) -> web.StreamResponse:
    parcel = await _shared(request)
    repo: ParcelRepository = bot_data(request)["parcel_repo"]
    settings: SettingsRepository = bot_data(request)["settings"]
    events = await repo.get_history(parcel.tracking_number, limit=100, user_id=parcel.user_id)
    return await page(
        request,
        "public.html",
        {
            "p": parcel,
            "events": events,
            "shop": await settings.shop_name(parcel.user_id),
            "token": request.match_info["token"],
        },
        public=True,
    )


async def tracking_map(request: web.Request) -> web.StreamResponse:
    return await map_response(request, await _shared(request))
