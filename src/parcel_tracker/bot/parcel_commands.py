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
    await repo.create(parcel)
    await update.message.reply_text(
        messages.parcel_added(name or tracking_number), parse_mode="HTML"
    )


async def cmd_list(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """List active parcels for the user."""
    user = update.effective_user
    if user is None or update.message is None:
        return
    repo = context.bot_data["parcel_repo"]
    parcels = await repo.list_active_for_user(user_id=user.id)
    if not parcels:
        await update.message.reply_text(messages.no_parcels_active(), parse_mode="HTML")
        return
    text = "\n".join(f"• <code>{p.tracking_number}</code> {p.name or ''}".rstrip() for p in parcels)
    await update.message.reply_text(text, parse_mode="HTML")


async def cmd_status(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show details of a single parcel."""
    if update.message is None:
        return
    args = context.args or []
    if not args:
        await update.message.reply_text(messages.status_usage(), parse_mode="HTML")
        return
    tracking_number = args[0].strip()
    repo = context.bot_data["parcel_repo"]
    parcel = await repo.get_by_tracking_number(tracking_number)
    if parcel is None:
        await update.message.reply_text(
            messages.parcel_not_found(tracking_number), parse_mode="HTML"
        )
        return
    text = (
        f"<b>{parcel.name or parcel.tracking_number}</b>\n"
        f"<code>{parcel.tracking_number}</code>\n"
        f"Status: <i>{parcel.status.value}</i>\n"
        f"{messages.carrier_label()}: {parcel.carrier_name or parcel.carrier_code or '?'}"
    )
    await update.message.reply_text(text, parse_mode="HTML")


async def cmd_events(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show event history for a parcel."""
    if update.message is None:
        return
    args = context.args or []
    if not args:
        await update.message.reply_text(messages.events_usage(), parse_mode="HTML")
        return
    tracking_number = args[0].strip()
    repo = context.bot_data["parcel_repo"]
    events = await repo.get_history(tracking_number, limit=20)
    if not events:
        await update.message.reply_text(messages.no_events(tracking_number), parse_mode="HTML")
        return
    lines = [messages.events_for(tracking_number)]
    for ev in events:
        line = f"• <i>{ev.time}</i> — {ev.description}"
        if ev.location:
            line += f" ({ev.location})"
        lines.append(line)
    await update.message.reply_text("\n".join(lines), parse_mode="HTML")


async def cmd_remove(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Remove (deactivate) a parcel."""
    if update.message is None:
        return
    args = context.args or []
    if not args:
        await update.message.reply_text(messages.remove_usage(), parse_mode="HTML")
        return
    tracking_number = args[0].strip()
    repo = context.bot_data["parcel_repo"]
    # TODO: actual remove method on repo. For now: mark as Expired as a stand-in.
    parcel = await repo.get_by_tracking_number(tracking_number)
    if parcel is None:
        await update.message.reply_text(
            messages.parcel_not_found(tracking_number), parse_mode="HTML"
        )
        return
    await repo.update_status(tracking_number, ShipmentStatus.EXPIRED)
    await update.message.reply_text(messages.parcel_removed(tracking_number), parse_mode="HTML")


async def cmd_rename(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Rename a parcel (requires repo.rename; stub reply for now)."""
    if update.message is None:
        return
    args = context.args or []
    if len(args) < 2:
        await update.message.reply_text(messages.rename_usage(), parse_mode="HTML")
        return
    tracking_number = args[0].strip()
    new_name = " ".join(args[1:]).strip()
    await update.message.reply_text(
        messages.parcel_renamed(tracking_number, new_name),
        parse_mode="HTML",
    )


async def cmd_checkall(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Trigger an update for all the user's parcels (scheduler call not wired yet)."""
    if update.message is None:
        return
    await update.message.reply_text(messages.checkall_started(), parse_mode="HTML")
    # TODO: enqueue background task
    await update.message.reply_text(messages.checkall_done(), parse_mode="HTML")


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle plain text — interpret as tracking number to add (detector not wired yet)."""
    if update.message is None or update.effective_user is None:
        return
    text = (update.message.text or "").strip()
    if not text:
        return
    logger.debug("handle_message received: %s", text)
    # For now: just echo back a hint. TODO: detector + create parcel.
    await update.message.reply_text(messages.to_add_use(text), parse_mode="HTML")
