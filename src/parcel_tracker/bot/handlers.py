"""Telegram handlers entry-point — registers all commands with the Application."""

from __future__ import annotations

import logging
from collections.abc import Callable, Coroutine
from typing import TYPE_CHECKING, Any

from telegram import Update
from telegram.ext import (
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from parcel_tracker.bot.admin_commands import (
    cmd_clean,
    cmd_cleanall,
    cmd_delivered,
    cmd_stats,
)
from parcel_tracker.bot.auth_commands import (
    cmd_adduser,
    cmd_removeuser,
    cmd_users,
    cmd_whoami,
)
from parcel_tracker.bot.callbacks import handle_callback
from parcel_tracker.bot.navigation_commands import (
    cmd_help,
    cmd_map,
    cmd_menu,
    cmd_start,
)
from parcel_tracker.bot.parcel_commands import (
    cmd_add,
    cmd_checkall,
    cmd_events,
    cmd_list,
    cmd_remove,
    cmd_rename,
    cmd_status,
    handle_message,
)

if TYPE_CHECKING:
    from telegram.ext import Application

    from parcel_tracker.config import Config
    from parcel_tracker.core.registry import TrackerRegistry
    from parcel_tracker.db.repository import ParcelRepository, UserRepository

logger = logging.getLogger(__name__)

# A Telegram command handler coroutine type alias matching CommandHandler's signature.
CommandFn = Callable[[Update, ContextTypes.DEFAULT_TYPE], Coroutine[Any, Any, None]]


def register_handlers(
    app: Application[Any, Any, Any, Any, Any, Any],
    *,
    config: Config,
    parcel_repo: ParcelRepository,
    user_repo: UserRepository,
    registry: TrackerRegistry,
) -> None:
    """Register all command, callback, and message handlers."""

    app.bot_data["config"] = config
    app.bot_data["parcel_repo"] = parcel_repo
    app.bot_data["user_repo"] = user_repo
    app.bot_data["registry"] = registry

    # Auth & navigation
    app.add_handler(CommandHandler("whoami", cmd_whoami))

    # Parcel & nav commands
    parcel_nav_cmds: list[tuple[str, CommandFn]] = [
        ("start", cmd_start),
        ("help", cmd_help),
        ("menu", cmd_menu),
        ("add", cmd_add),
        ("list", cmd_list),
        ("status", cmd_status),
        ("events", cmd_events),
        ("map", cmd_map),
        ("remove", cmd_remove),
        ("rename", cmd_rename),
        ("checkall", cmd_checkall),
        ("delivered", cmd_delivered),
        ("clean", cmd_clean),
        ("cleanall", cmd_cleanall),
        ("stats", cmd_stats),
    ]
    for cmd, fn in parcel_nav_cmds:
        app.add_handler(CommandHandler(cmd, fn))

    # Admin user commands
    auth_cmds: list[tuple[str, CommandFn]] = [
        ("adduser", cmd_adduser),
        ("removeuser", cmd_removeuser),
        ("users", cmd_users),
    ]
    for cmd, fn in auth_cmds:
        app.add_handler(CommandHandler(cmd, fn))

    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.add_handler(CallbackQueryHandler(handle_callback))

    logger.info("Handlers registered")
