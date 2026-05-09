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
    if user is None or update.message is None:
        return
    if not _is_owner(context, user.id):
        await update.message.reply_text(messages.owner_only(), parse_mode="HTML")
        return
    # Phase 2: actual cleaning logic via repo.archive_old / repo.delete_inactive
    await update.message.reply_text(messages.clean_done(), parse_mode="HTML")


async def cmd_cleanall(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Remove all parcels (owner only — DANGEROUS)."""
    user = update.effective_user
    if user is None or update.message is None:
        return
    if not _is_owner(context, user.id):
        await update.message.reply_text(messages.owner_only(), parse_mode="HTML")
        return
    # Phase 2: actual delete-all logic
    await update.message.reply_text(messages.cleanall_done(), parse_mode="HTML")


async def cmd_delivered(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show delivered parcels for the user."""
    user = update.effective_user
    if user is None or update.message is None:
        return
    repo = context.bot_data["parcel_repo"]
    parcels = await repo.list_active_for_user(user_id=user.id)
    delivered = [p for p in parcels if p.status.value == "Delivered"]
    if not delivered:
        await update.message.reply_text(messages.no_delivered_parcels(), parse_mode="HTML")
        return
    text = "\n".join(
        f"✅ <code>{p.tracking_number}</code> {p.name or ''}".rstrip() for p in delivered
    )
    await update.message.reply_text(text, parse_mode="HTML")


async def cmd_stats(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show bot stats (owner only)."""
    user = update.effective_user
    if user is None or update.message is None:
        return
    if not _is_owner(context, user.id):
        await update.message.reply_text(messages.owner_only(), parse_mode="HTML")
        return
    user_repo = context.bot_data["user_repo"]
    user_ids = await user_repo.get_allowed_user_ids()
    text = f"{messages.stats_header()}\n\n{messages.authorised_users_count(len(user_ids))}"
    await update.message.reply_text(text, parse_mode="HTML")
