"""/forgetme — let a user erase everything the bot stores about them."""

from __future__ import annotations

from typing import TYPE_CHECKING

from telegram import InlineKeyboardButton, InlineKeyboardMarkup

from parcel_tracker.bot import messages
from parcel_tracker.i18n import _

if TYPE_CHECKING:
    from telegram import Update
    from telegram.ext import ContextTypes


def forgetme_confirm() -> InlineKeyboardMarkup:
    """Confirmation step: erasure cannot be undone."""
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton(_("🗑 Yes, delete my data"), callback_data="action:forgetme_do")],
            [InlineKeyboardButton(_("⬅️ Cancel"), callback_data="nav:main")],
        ]
    )


async def cmd_forgetme(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Ask for confirmation; the erasure itself runs on the confirm button."""
    reply_to = update.effective_message
    if reply_to is None or update.effective_user is None:
        return
    await reply_to.reply_text(
        messages.forgetme_confirm_prompt(), parse_mode="HTML", reply_markup=forgetme_confirm()
    )


async def erase_my_data(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Confirmed /forgetme: delete the caller's data (never anyone else's)."""
    query = update.callback_query
    user = update.effective_user
    if query is None or user is None:
        return
    if context.user_data is not None:
        context.user_data.clear()  # drop any pending guided input too
    await context.bot_data["user_repo"].erase_user_data(user.id)
    await query.edit_message_text(messages.forgetme_done(), parse_mode="HTML")
