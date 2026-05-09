"""Telegram /notify command family: menu + quick on/off/all/none + callback toggle."""

from __future__ import annotations

import logging

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

from parcel_tracker.db.models import ShipmentStatus

logger = logging.getLogger(__name__)


_NOTIFIABLE_STATUS = [s for s in ShipmentStatus if s is not ShipmentStatus.NOT_FOUND]
_DEFAULT_ON_VALUES = {
    ShipmentStatus.DELIVERED.value,
    ShipmentStatus.EXCEPTION.value,
    ShipmentStatus.OUT_FOR_DELIVERY.value,
    ShipmentStatus.RETURNED.value,
}


def _resolve_enabled(prefs: dict[str, bool], status: ShipmentStatus) -> bool:
    if status.value in prefs:
        return prefs[status.value]
    return status.value in _DEFAULT_ON_VALUES


def _build_keyboard(prefs: dict[str, bool]) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    for status in _NOTIFIABLE_STATUS:
        on = _resolve_enabled(prefs, status)
        marker = "✅" if on else "▫️"
        rows.append(
            [
                InlineKeyboardButton(
                    f"{marker} {status.value}",
                    callback_data=f"notify:{status.value}",
                )
            ]
        )
    return InlineKeyboardMarkup(rows)


async def cmd_notify(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """`/notify` — show the inline keyboard menu of notifiable statuses."""
    if update.message is None:
        return
    user_id = update.effective_user.id if update.effective_user else 0
    repo = context.bot_data["notification_repo"]
    prefs: dict[str, bool] = await repo.get_all_prefs(user_id)
    keyboard = _build_keyboard(prefs)
    await update.message.reply_text(
        "🔔 <b>Notification preferences</b>\n\nTap a status to toggle on/off.",
        parse_mode="HTML",
        reply_markup=keyboard,
    )


async def cmd_notify_dispatch(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Dispatch /notify subcommands: all, none, on <status>, off <status>, default → menu."""
    if update.message is None:
        return
    if not context.args:
        await cmd_notify(update, context)
        return

    user_id = update.effective_user.id if update.effective_user else 0
    repo = context.bot_data["notification_repo"]
    sub = context.args[0].lower()

    if sub == "all":
        for status in _NOTIFIABLE_STATUS:
            await repo.set_pref(user_id=user_id, status_value=status.value, enabled=True)
        await update.message.reply_text("✅ All notifications enabled.")
        return

    if sub == "none":
        for status in _NOTIFIABLE_STATUS:
            await repo.set_pref(user_id=user_id, status_value=status.value, enabled=False)
        await update.message.reply_text("🔇 All notifications disabled.")
        return

    if sub in {"on", "off"} and len(context.args) >= 2:
        target = context.args[1]
        match = next(
            (s for s in _NOTIFIABLE_STATUS if s.value.lower() == target.lower()),
            None,
        )
        if match is None:
            valid = ", ".join(s.value for s in _NOTIFIABLE_STATUS)
            await update.message.reply_text(f"❌ Unknown status. Valid: {valid}.")
            return
        enabled = sub == "on"
        await repo.set_pref(user_id=user_id, status_value=match.value, enabled=enabled)
        verb = "enabled" if enabled else "disabled"
        await update.message.reply_text(f"🔔 <code>{match.value}</code> {verb}.", parse_mode="HTML")
        return

    await cmd_notify(update, context)


async def on_notify_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Inline button tap toggles a status pref."""
    query = update.callback_query
    if query is None or query.data is None:
        return
    if not query.data.startswith("notify:"):
        return

    status_value = query.data.split(":", 1)[1]
    if query.from_user is None:
        return
    user_id = query.from_user.id
    repo = context.bot_data["notification_repo"]

    current = await repo.get_pref(user_id, status_value)
    if current is None:
        current = status_value in _DEFAULT_ON_VALUES
    new_value = not current
    await repo.set_pref(user_id=user_id, status_value=status_value, enabled=new_value)

    await query.answer(f"{status_value} → {'on' if new_value else 'off'}")

    prefs: dict[str, bool] = await repo.get_all_prefs(user_id)
    keyboard = _build_keyboard(prefs)
    await query.edit_message_text(
        "🔔 <b>Notification preferences</b>\n\nTap a status to toggle on/off.",
        parse_mode="HTML",
        reply_markup=keyboard,
    )
