"""Web dashboard: a private view of your shipments plus public tracking pages.

Runs inside the bot's own event loop (aiohttp), so it shares the database, the
trackers and the notifier with the Telegram side. Opt-in with WEB_ENABLED=true.
"""

from parcel_tracker.web.server import WebServer

__all__ = ["WebServer"]
