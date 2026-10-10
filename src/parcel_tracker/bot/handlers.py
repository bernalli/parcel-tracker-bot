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
    TypeHandler,
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
from parcel_tracker.bot.auth_gate import AUTH_GATE_GROUP, authorization_gate
from parcel_tracker.bot.callbacks import handle_callback
from parcel_tracker.bot.lang_command import cmd_lang
from parcel_tracker.bot.language import LANGUAGE_GROUP, apply_user_language
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
    cmd_history,
    cmd_list,
    cmd_remove,
    cmd_rename,
    cmd_status,
    handle_message,
)
from parcel_tracker.bot.privacy_commands import cmd_forgetme
from parcel_tracker.bot.seller_commands import cmd_export, cmd_web, handle_csv_document

if TYPE_CHECKING:
    from telegram.ext import Application

    from parcel_tracker.config import Config
    from parcel_tracker.core.registry import TrackerRegistry
    from parcel_tracker.db.repository import ParcelRepository, UserRepository

logger = logging.getLogger(__name__)

# Edited messages are ignored: re-running an edited /remove or /checkall (or
# re-adding an edited code) is never what the user meant.
NEW_MESSAGES = filters.UpdateType.MESSAGE

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

    # Authorization gate: runs before every other handler group and stops updates
    # from users who are not owner/admin/allow-listed (see bot/auth_gate.py).
    app.add_handler(TypeHandler(Update, authorization_gate), group=AUTH_GATE_GROUP)
    # Then the sender's language, so every reply uses it instead of a
    # process-wide one (see bot/language.py).
    app.add_handler(TypeHandler(Update, apply_user_language), group=LANGUAGE_GROUP)

    # Auth & navigation
    app.add_handler(CommandHandler("whoami", cmd_whoami, filters=NEW_MESSAGES))
    app.add_handler(CommandHandler("lang", cmd_lang, filters=NEW_MESSAGES))

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
        ("history", cmd_history),
        ("delivered", cmd_delivered),
        ("clean", cmd_clean),
        ("cleanall", cmd_cleanall),
        ("stats", cmd_stats),
        ("forgetme", cmd_forgetme),
        ("web", cmd_web),
        ("export", cmd_export),
    ]
    for cmd, fn in parcel_nav_cmds:
        app.add_handler(CommandHandler(cmd, fn, filters=NEW_MESSAGES))

    # Admin user commands
    auth_cmds: list[tuple[str, CommandFn]] = [
        ("adduser", cmd_adduser),
        ("removeuser", cmd_removeuser),
        ("users", cmd_users),
    ]
    for cmd, fn in auth_cmds:
        app.add_handler(CommandHandler(cmd, fn, filters=NEW_MESSAGES))

    # Auto-add only in private chats: in a group every ordinary message would get
    # a "to add, use /add …" reply.
    app.add_handler(
        MessageHandler(
            filters.TEXT & ~filters.COMMAND & filters.ChatType.PRIVATE & NEW_MESSAGES,
            handle_message,
        )
    )
    # A CSV file sent in a private chat is imported as shipments.
    app.add_handler(
        MessageHandler(
            filters.Document.FileExtension("csv") & filters.ChatType.PRIVATE & NEW_MESSAGES,
            handle_csv_document,
        )
    )
    # Pattern-restricted catch-all: only handle the four prefixes we own.
    # Other prefix-specific handlers (notify:*) are registered later in main.py
    # and must not be shadowed by an unrestricted CallbackQueryHandler.
    app.add_handler(
        CallbackQueryHandler(
            handle_callback, pattern=r"^(nav|action|prompt|parcel|confirm|setlang|detail):"
        )
    )

    logger.info("Handlers registered")
