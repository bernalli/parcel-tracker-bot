"""Navigation commands: start, help, menu, map."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from parcel_tracker.bot import messages
from parcel_tracker.bot.keyboards import main_menu

if TYPE_CHECKING:
    from telegram import Update
    from telegram.ext import ContextTypes

logger = logging.getLogger(__name__)


async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """/start — welcome message."""
    if update.message is None:
        return
    await update.message.reply_text(messages.welcome(), parse_mode="HTML")


async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """/help — list available commands."""
    if update.message is None:
        return
    await update.message.reply_text(messages.help_text(), parse_mode="HTML")


async def cmd_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """/menu — interactive inline menu."""
    if update.message is None:
        return
    await update.message.reply_text(
        messages.menu_header(), reply_markup=main_menu(), parse_mode="HTML"
    )


async def cmd_map(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """/map — placeholder for parcel map view (Phase 3)."""
    if update.message is None:
        return
    await update.message.reply_text(messages.map_placeholder(), parse_mode="HTML")
