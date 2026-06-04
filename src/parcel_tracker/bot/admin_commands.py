"""Admin commands: clean, cleanall, delivered, stats."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from parcel_tracker.bot import messages

if TYPE_CHECKING:
    from telegram import Update
    from telegram.ext import ContextTypes

logger = logging.getLogger(__name__)


def _is_owner(context: Any, user_id: int) -> bool:
    config = context.bot_data.get("config")
    if config is None:
        return False
    return bool(getattr(config, "owner_id", None) == user_id)


async def cmd_clean(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Clean delivered/expired parcels (owner only)."""
    user = update.effective_user
    reply_to = update.effective_message
    if user is None or reply_to is None:
        return
    if not _is_owner(context, user.id):
        await reply_to.reply_text(messages.owner_only(), parse_mode="HTML")
        return
    repo = context.bot_data["parcel_repo"]
    await repo.archive_delivered_for_user(user_id=user.id)
    await reply_to.reply_text(messages.clean_done(), parse_mode="HTML")


async def cmd_cleanall(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Remove all parcels (owner only — DANGEROUS)."""
    user = update.effective_user
    reply_to = update.effective_message
    if user is None or reply_to is None:
        return
    if not _is_owner(context, user.id):
        await reply_to.reply_text(messages.owner_only(), parse_mode="HTML")
        return
    repo = context.bot_data["parcel_repo"]
    await repo.archive_delivered_for_user(user_id=user.id)
    await reply_to.reply_text(messages.cleanall_done(), parse_mode="HTML")


async def cmd_delivered(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show delivered parcels (active + archived) for the user."""
    user = update.effective_user
    reply_to = update.effective_message
    if user is None or reply_to is None:
        return
    repo = context.bot_data["parcel_repo"]
    active = await repo.list_active_for_user(user_id=user.id)
    archived = await repo.list_archived_for_user(user_id=user.id)
    delivered = [p for p in active if p.status.value == "Delivered"] + list(archived)
    if not delivered:
        await reply_to.reply_text(messages.no_delivered_parcels(), parse_mode="HTML")
        return
    text = "\n".join(
        f"✅ <code>{messages.esc(p.tracking_number)}</code> {messages.esc(p.name or '')}".rstrip()
        for p in delivered
    )
    await reply_to.reply_text(text, parse_mode="HTML")


async def cmd_stats(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show bot stats (owner only)."""
    user = update.effective_user
    reply_to = update.effective_message
    if user is None or reply_to is None:
        return
    if not _is_owner(context, user.id):
        await reply_to.reply_text(messages.owner_only(), parse_mode="HTML")
        return
    user_repo = context.bot_data["user_repo"]
    user_ids = await user_repo.get_allowed_user_ids()
    text = f"{messages.stats_header()}\n\n{messages.authorised_users_count(len(user_ids))}"
    await reply_to.reply_text(text, parse_mode="HTML")
