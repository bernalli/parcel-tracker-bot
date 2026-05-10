"""Navigation commands: start, help, menu, map."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from parcel_tracker.bot import messages
from parcel_tracker.bot.keyboards import main_menu

if TYPE_CHECKING:
    from telegram import Update
    from telegram.ext import ContextTypes

    from parcel_tracker.config import Config

logger = logging.getLogger(__name__)


def _is_admin(user_id: int, config: Config) -> bool:
    return user_id in config.admin_user_ids


async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """/start — welcome message."""
    if update.message is None:
        return
    await update.message.reply_text(messages.welcome(), parse_mode="HTML")


async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """/help — list available commands."""
    reply_to = update.effective_message
    if reply_to is None:
        return
    await reply_to.reply_text(messages.help_text(), parse_mode="HTML")


async def cmd_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """/menu — interactive inline menu."""
    if update.message is None or update.effective_user is None:
        return
    config = context.bot_data["config"]
    is_admin = _is_admin(update.effective_user.id, config)
    await update.message.reply_text(
        messages.menu_header(),
        reply_markup=main_menu(is_admin=is_admin),
        parse_mode="HTML",
    )


async def cmd_map(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """/map — placeholder for parcel map view."""
    reply_to = update.effective_message
    if reply_to is None:
        return
    await reply_to.reply_text(messages.map_placeholder(), parse_mode="HTML")
