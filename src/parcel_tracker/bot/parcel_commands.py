"""Parcel-related commands: add, list, status, events, remove, rename, checkall."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from parcel_tracker.bot import messages
from parcel_tracker.db.models import Parcel, ShipmentStatus

if TYPE_CHECKING:
    from telegram import Update
    from telegram.ext import ContextTypes

logger = logging.getLogger(__name__)


async def cmd_add(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Add a new parcel for the user. Args: tracking_number [name] [carrier]."""
    user = update.effective_user
    if user is None or update.message is None:
        return
    args = context.args or []
    if not args:
        await update.message.reply_text(messages.add_usage(), parse_mode="HTML")
        return
    tracking_number = args[0].strip()
    name = args[1] if len(args) >= 2 else None
    carrier = args[2] if len(args) >= 3 else None

    repo = context.bot_data["parcel_repo"]
    parcel = Parcel(
        tracking_number=tracking_number,
        user_id=user.id,
        name=name,
        carrier_code=carrier,
    )
    created = await repo.create(parcel)
    if created is None:
        await update.message.reply_text(
            messages.parcel_duplicate(tracking_number), parse_mode="HTML"
        )
        return
    await update.message.reply_text(
        messages.parcel_added(name or tracking_number), parse_mode="HTML"
    )


async def cmd_list(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """List active parcels for the user."""
    user = update.effective_user
    reply_to = update.effective_message
    if user is None or reply_to is None:
        return
    repo = context.bot_data["parcel_repo"]
    parcels = await repo.list_active_for_user(user_id=user.id)
    if not parcels:
        await reply_to.reply_text(messages.no_parcels_active(), parse_mode="HTML")
        return
    text = "\n".join(f"• <code>{p.tracking_number}</code> {p.name or ''}".rstrip() for p in parcels)
    await reply_to.reply_text(text, parse_mode="HTML")


async def cmd_status(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show details of a single parcel."""
    reply_to = update.effective_message
    if reply_to is None:
        return
    args = context.args or []
    if not args:
        await reply_to.reply_text(messages.status_usage(), parse_mode="HTML")
        return
    tracking_number = args[0].strip()
    repo = context.bot_data["parcel_repo"]
    parcel = await repo.get_by_tracking_number(tracking_number)
    if parcel is None:
        await reply_to.reply_text(messages.parcel_not_found(tracking_number), parse_mode="HTML")
        return
    text = (
        f"<b>{parcel.name or parcel.tracking_number}</b>\n"
        f"<code>{parcel.tracking_number}</code>\n"
        f"Status: <i>{parcel.status.value}</i>\n"
        f"{messages.carrier_label()}: {parcel.carrier_name or parcel.carrier_code or '?'}"
    )
    await reply_to.reply_text(text, parse_mode="HTML")


async def cmd_events(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show event history for a parcel."""
    reply_to = update.effective_message
    if reply_to is None:
        return
    args = context.args or []
    if not args:
        await reply_to.reply_text(messages.events_usage(), parse_mode="HTML")
        return
    tracking_number = args[0].strip()
    repo = context.bot_data["parcel_repo"]
    events = await repo.get_history(tracking_number, limit=20)
    if not events:
        await reply_to.reply_text(messages.no_events(tracking_number), parse_mode="HTML")
        return
    lines = [messages.events_for(tracking_number)]
    for ev in events:
        line = f"• <i>{ev.time}</i> — {ev.description}"
        if ev.location:
            line += f" ({ev.location})"
        lines.append(line)
    await reply_to.reply_text("\n".join(lines), parse_mode="HTML")


async def cmd_remove(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Remove (deactivate) a parcel."""
    reply_to = update.effective_message
    if reply_to is None:
        return
    args = context.args or []
    if not args:
        await reply_to.reply_text(messages.remove_usage(), parse_mode="HTML")
        return
    tracking_number = args[0].strip()
    repo = context.bot_data["parcel_repo"]
    # Phase 2: actual remove method on repo. F1: mark as Expired as a stand-in.
    parcel = await repo.get_by_tracking_number(tracking_number)
    if parcel is None:
        await reply_to.reply_text(messages.parcel_not_found(tracking_number), parse_mode="HTML")
        return
    await repo.update_status(tracking_number, ShipmentStatus.EXPIRED)
    await reply_to.reply_text(messages.parcel_removed(tracking_number), parse_mode="HTML")


async def cmd_rename(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Rename a parcel (Phase 2: requires repo.rename method; F1: stub reply)."""
    reply_to = update.effective_message
    if reply_to is None:
        return
    args = context.args or []
    if len(args) < 2:
        await reply_to.reply_text(messages.rename_usage(), parse_mode="HTML")
        return
    tracking_number = args[0].strip()
    new_name = " ".join(args[1:]).strip()
    await reply_to.reply_text(
        messages.parcel_renamed(tracking_number, new_name),
        parse_mode="HTML",
    )


async def cmd_checkall(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Trigger an update for all the user's parcels (Phase 2: actual scheduler call)."""
    reply_to = update.effective_message
    if reply_to is None:
        return
    await reply_to.reply_text(messages.checkall_started(), parse_mode="HTML")
    # Phase 2: enqueue background task
    await reply_to.reply_text(messages.checkall_done(), parse_mode="HTML")


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle plain text — interpret as tracking number to add (Phase 2: detector)."""
    if update.message is None or update.effective_user is None:
        return
    text = (update.message.text or "").strip()
    if not text:
        return
    logger.debug("handle_message received: %s", text)
    # F1 minimal: just echo back a hint. Phase 2: detector + create parcel.
    await update.message.reply_text(messages.to_add_use(text), parse_mode="HTML")
