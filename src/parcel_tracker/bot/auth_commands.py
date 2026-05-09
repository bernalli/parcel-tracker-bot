"""Auth-related commands: whoami, adduser, removeuser, users."""

from __future__ import annotations

import logging
from typing import Any

from telegram import Update
from telegram.ext import ContextTypes

from parcel_tracker.bot import messages

logger = logging.getLogger(__name__)


def _is_owner(context: Any, user_id: int) -> bool:
    """Check whether the given user_id matches the configured owner."""
    config = context.bot_data.get("config")
    if config is None:
        return False
    return bool(getattr(config, "owner_id", None) == user_id)


async def cmd_whoami(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Reply with the user's Telegram ID and username."""
    user = update.effective_user
    if user is None or update.message is None:
        return
    username = f"@{user.username}" if user.username else "(no username)"
    text = f"Your ID: <code>{user.id}</code>\nUsername: {username}"
    await update.message.reply_text(text, parse_mode="HTML")


async def cmd_adduser(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Add a user to the allowed list (owner only)."""
    user = update.effective_user
    if user is None or update.message is None:
        return
    if not _is_owner(context, user.id):
        await update.message.reply_text(messages.owner_only(), parse_mode="HTML")
        return

    args = context.args or []
    if not args:
        await update.message.reply_text(messages.adduser_usage(), parse_mode="HTML")
        return
    try:
        new_user_id = int(args[0])
    except ValueError:
        await update.message.reply_text(messages.adduser_usage(), parse_mode="HTML")
        return

    user_repo = context.bot_data["user_repo"]
    added = await user_repo.add_user(user_id=new_user_id, added_by=user.id)
    if added:
        await update.message.reply_text(messages.user_added(new_user_id), parse_mode="HTML")
    else:
        await update.message.reply_text(messages.user_duplicate(new_user_id), parse_mode="HTML")


async def cmd_removeuser(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Remove a user from the allowed list (owner only)."""
    user = update.effective_user
    if user is None or update.message is None:
        return
    if not _is_owner(context, user.id):
        await update.message.reply_text(messages.owner_only(), parse_mode="HTML")
        return

    args = context.args or []
    if not args:
        await update.message.reply_text(messages.removeuser_usage(), parse_mode="HTML")
        return
    try:
        target_user_id = int(args[0])
    except ValueError:
        await update.message.reply_text(messages.removeuser_usage(), parse_mode="HTML")
        return

    user_repo = context.bot_data["user_repo"]
    await user_repo.remove_user(target_user_id)
    await update.message.reply_text(messages.user_removed(target_user_id), parse_mode="HTML")


async def cmd_users(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """List allowed users (owner only)."""
    user = update.effective_user
    if user is None or update.message is None:
        return
    if not _is_owner(context, user.id):
        await update.message.reply_text(messages.owner_only(), parse_mode="HTML")
        return

    user_repo = context.bot_data["user_repo"]
    user_ids = await user_repo.get_allowed_user_ids()
    if not user_ids:
        await update.message.reply_text(messages.no_users(), parse_mode="HTML")
        return
    text = "\n".join(f"• <code>{uid}</code>" for uid in user_ids)
    await update.message.reply_text(text, parse_mode="HTML")
