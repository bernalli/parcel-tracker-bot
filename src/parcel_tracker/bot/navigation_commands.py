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
    """/map CODE — on-demand best-effort map of a parcel's last known position."""
    user = update.effective_user
    reply_to = update.effective_message
    if user is None or reply_to is None:
        return
    args = context.args or []
    if not args:
        await reply_to.reply_text(messages.map_usage(), parse_mode="HTML")
        return
    tracking_number = args[0].strip()
    repo = context.bot_data["parcel_repo"]
    parcel = await repo.get_for_user(tracking_number, user_id=user.id)
    if parcel is None:
        await reply_to.reply_text(
            messages.parcel_not_found(tracking_number), parse_mode="HTML"
        )
        return
    geocoder = context.bot_data.get("geocoder")
    map_renderer = context.bot_data.get("map_renderer")
    coord = (
        geocoder.geocode(parcel.last_location)
        if (geocoder and parcel.last_location)
        else None
    )
    if coord is None or map_renderer is None:
        await reply_to.reply_text(
            messages.map_no_position(tracking_number), parse_mode="HTML"
        )
        return
    import asyncio  # noqa: PLC0415

    from parcel_tracker.maps.transport import infer_transport_mode  # noqa: PLC0415

    mode = infer_transport_mode(parcel.carrier_name, parcel.last_event)
    png = await asyncio.to_thread(
        map_renderer.render, lat=coord[0], lng=coord[1], mode=mode
    )
    await context.bot.send_photo(
        chat_id=reply_to.chat_id,
        photo=png,
        caption=f"📍 {messages.esc(parcel.last_location)}",
        parse_mode="HTML",
    )
