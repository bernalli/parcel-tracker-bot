"""Typed keys for state stored on the aiohttp application and requests."""

from __future__ import annotations

from collections import OrderedDict
from typing import Any

import jinja2
from aiohttp import web

from parcel_tracker.db.web_repository import WebSession

BOT_DATA = web.AppKey("bot_data", dict[str, Any])
JINJA = web.AppKey("jinja", jinja2.Environment)
MAP_CACHE = web.AppKey("map_cache", OrderedDict[tuple[int, str, str], bytes | None])
SESSION = web.RequestKey("session", WebSession)
API_USER = web.RequestKey("api_user_id", int)
