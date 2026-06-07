"""Parcel-related commands: add, list, status, events, remove, rename, checkall."""

from __future__ import annotations

import logging
import re
from typing import TYPE_CHECKING

from parcel_tracker.bot import messages
from parcel_tracker.db.models import Parcel

if TYPE_CHECKING:
    from telegram import Update
    from telegram.ext import ContextTypes

logger = logging.getLogger(__name__)

_TRACKING_SHAPE = re.compile(r"^[A-Z0-9]{8,35}$")


def _looks_like_tracking(candidate: str) -> bool:
    """Strict heuristic: alphanumeric, 8-35 chars, with at least 3 digits."""
    up = candidate.upper()
    if not _TRACKING_SHAPE.fullmatch(up):
        return False
    return sum(c.isdigit() for c in up) >= 3


_NAME_MAX_LEN = 64


async def cmd_add(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Add a new parcel for the user. Args: tracking_number [name…] (multi-word name)."""
    user = update.effective_user
    if user is None or update.message is None:
        return
    args = context.args or []
    if not args:
        await update.message.reply_text(messages.add_usage(), parse_mode="HTML")
        return
    tracking_number = args[0].strip()
    name = " ".join(args[1:]).strip()[:_NAME_MAX_LEN] or None

    repo = context.bot_data["parcel_repo"]
    parcel = Parcel(
        tracking_number=tracking_number,
        user_id=user.id,
        name=name,
    )
    created = await repo.create(parcel)
    if created is None:
        await update.message.reply_text(
            messages.parcel_duplicate(tracking_number), parse_mode="HTML"
        )
        return
    if name is None:
        from parcel_tracker.bot.keyboards import name_prompt_keyboard  # noqa: PLC0415

        if context.user_data is not None:
            context.user_data["pending"] = {"action": "name", "tn": tracking_number}
        await update.message.reply_text(
            messages.parcel_added(tracking_number) + "\n\n" + messages.ask_parcel_name(),
            parse_mode="HTML",
            reply_markup=name_prompt_keyboard(tracking_number),
        )
        return
    await update.message.reply_text(messages.parcel_added(name), parse_mode="HTML")


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
    text = "\n".join(
        f"• <code>{messages.esc(p.tracking_number)}</code> {messages.esc(p.name or '')}".rstrip()
        for p in parcels
    )
    await reply_to.reply_text(text, parse_mode="HTML")


async def cmd_status(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show details of a single parcel."""
    user = update.effective_user
    reply_to = update.effective_message
    if user is None or reply_to is None:
        return
    args = context.args or []
    if not args:
        await reply_to.reply_text(messages.status_usage(), parse_mode="HTML")
        return
    tracking_number = args[0].strip()
    repo = context.bot_data["parcel_repo"]
    parcel = await repo.get_for_user(tracking_number, user_id=user.id)
    if parcel is None:
        await reply_to.reply_text(messages.parcel_not_found(tracking_number), parse_mode="HTML")
        return
    lines = [
        f"<b>{messages.esc(parcel.name or parcel.tracking_number)}</b>",
        f"<code>{messages.esc(parcel.tracking_number)}</code>",
        f"Status: <i>{parcel.status.value}</i>",
        f"{messages.carrier_label()}: {messages.esc(parcel.carrier_name or parcel.carrier_code or '?')}",
    ]
    if parcel.last_location:
        lines.append(f"📍 {messages.esc(parcel.last_location)}")
    if parcel.last_event:
        lines.append(f"🛈 {messages.esc(parcel.last_event)}")
    text = "\n".join(lines)
    await reply_to.reply_text(text, parse_mode="HTML")


async def cmd_events(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show event history for a parcel."""
    user = update.effective_user
    reply_to = update.effective_message
    if user is None or reply_to is None:
        return
    args = context.args or []
    if not args:
        await reply_to.reply_text(messages.events_usage(), parse_mode="HTML")
        return
    tracking_number = args[0].strip()
    repo = context.bot_data["parcel_repo"]
    parcel = await repo.get_for_user(tracking_number, user_id=user.id)
    if parcel is None:
        await reply_to.reply_text(messages.parcel_not_found(tracking_number), parse_mode="HTML")
        return
    events = await repo.get_history(tracking_number, limit=20)
    if not events:
        await reply_to.reply_text(messages.no_events(tracking_number), parse_mode="HTML")
        return
    lines = [messages.events_for(tracking_number)]
    for ev in events:
        line = f"• <i>{messages.esc(ev.time)}</i> — {messages.esc(ev.description)}"
        if ev.location:
            line += f" ({messages.esc(ev.location)})"
        lines.append(line)
    await reply_to.reply_text("\n".join(lines), parse_mode="HTML")


async def cmd_remove(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Remove (deactivate) a parcel."""
    user = update.effective_user
    reply_to = update.effective_message
    if user is None or reply_to is None:
        return
    args = context.args or []
    if not args:
        await reply_to.reply_text(messages.remove_usage(), parse_mode="HTML")
        return
    tracking_number = args[0].strip()
    repo = context.bot_data["parcel_repo"]
    parcel = await repo.get_for_user(tracking_number, user_id=user.id)
    if parcel is None:
        await reply_to.reply_text(messages.parcel_not_found(tracking_number), parse_mode="HTML")
        return
    await repo.deactivate(tracking_number)
    await reply_to.reply_text(messages.parcel_removed(tracking_number), parse_mode="HTML")


async def cmd_rename(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Rename a parcel (ownership-scoped, persisted)."""
    user = update.effective_user
    reply_to = update.effective_message
    if user is None or reply_to is None:
        return
    args = context.args or []
    if len(args) < 2:
        await reply_to.reply_text(messages.rename_usage(), parse_mode="HTML")
        return
    tracking_number = args[0].strip()
    new_name = " ".join(args[1:]).strip()
    repo = context.bot_data["parcel_repo"]
    ok = await repo.rename(tracking_number, user_id=user.id, name=new_name)
    if not ok:
        await reply_to.reply_text(messages.parcel_not_found(tracking_number), parse_mode="HTML")
        return
    await reply_to.reply_text(messages.parcel_renamed(tracking_number, new_name), parse_mode="HTML")


async def cmd_checkall(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Trigger an immediate update for all the user's parcels."""
    # Lazy import to avoid circular dependency (scheduler → notifier → bot → parcel_commands).
    # check_user_now is also looked up via globals() so tests can monkeypatch it.
    from parcel_tracker.core import scheduler as _sched  # noqa: PLC0415

    _fn = globals().get("check_user_now", _sched.check_user_now)

    user = update.effective_user
    reply_to = update.effective_message
    if user is None or reply_to is None:
        return
    await reply_to.reply_text(messages.checkall_started(), parse_mode="HTML")
    try:
        n = await _fn(context.bot_data, user_id=user.id)
    except Exception:  # noqa: BLE001 — surface a friendly message, never crash the handler
        logger.exception("checkall failed for user %s", user.id)
        await reply_to.reply_text(messages.generic_error(), parse_mode="HTML")
        return
    await reply_to.reply_text(messages.checkall_done_count(n), parse_mode="HTML")


async def cmd_history(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """List archived (delivered) parcels for the user."""
    user = update.effective_user
    reply_to = update.effective_message
    if user is None or reply_to is None:
        return
    repo = context.bot_data["parcel_repo"]
    parcels = await repo.list_archived_for_user(user_id=user.id)
    if not parcels:
        await reply_to.reply_text(messages.no_history(), parse_mode="HTML")
        return
    lines = [messages.history_header()]
    for p in parcels:
        lines.append(
            f"✅ <code>{messages.esc(p.tracking_number)}</code> {messages.esc(p.name or '')}".rstrip()
        )
    await reply_to.reply_text("\n".join(lines), parse_mode="HTML")


async def _consume_pending(update: Update, context: ContextTypes.DEFAULT_TYPE, text: str) -> bool:
    """If a guided input is pending for this user, consume `text` as its value.
    Returns True if it handled the message."""
    pending = (context.user_data or {}).get("pending")
    if not pending:
        return False
    user = update.effective_user
    reply_to = update.message
    if user is None or reply_to is None:
        return True
    action = pending.get("action")
    if context.user_data is not None:
        context.user_data.pop("pending", None)  # consume once
    repo = context.bot_data["parcel_repo"]
    if action == "rename":
        ok = await repo.rename(pending["tn"], user_id=user.id, name=text)
        msg = (
            messages.parcel_renamed(pending["tn"], text)
            if ok
            else messages.parcel_not_found(pending["tn"])
        )
        await reply_to.reply_text(msg, parse_mode="HTML")
        return True
    if action == "adduser":
        user_repo = context.bot_data["user_repo"]
        try:
            target = int(text.strip())
        except ValueError:
            await reply_to.reply_text(messages.adduser_usage(), parse_mode="HTML")
            return True
        added = await user_repo.add_user(user_id=target, added_by=user.id)
        await reply_to.reply_text(
            messages.user_added(target) if added else messages.user_duplicate(target),
            parse_mode="HTML",
        )
        return True
    if action == "revoke":
        user_repo = context.bot_data["user_repo"]
        try:
            target = int(text.strip())
        except ValueError:
            await reply_to.reply_text(messages.removeuser_usage(), parse_mode="HTML")
            return True
        removed = await user_repo.remove_user(target)
        await reply_to.reply_text(
            messages.user_removed(target) if removed else messages.user_not_present(target),
            parse_mode="HTML",
        )
        return True
    return True


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Plain text → if it looks like a tracking number, auto-add it (no /add needed)."""
    if update.message is None or update.effective_user is None:
        return
    text = (update.message.text or "").strip()
    if not text:
        return
    if await _consume_pending(update, context, text):
        return
    candidate = text.split()[0]
    name = text[len(candidate) :].strip() or None

    detector = context.bot_data.get("detector")
    specific_match = False
    if detector is not None:
        specific_match = any(t.priority > 1 for t in detector.detect(candidate))

    if not (specific_match or _looks_like_tracking(candidate)):
        await update.message.reply_text(messages.to_add_use(candidate), parse_mode="HTML")
        return

    name = name[:_NAME_MAX_LEN] if name else None
    tn = candidate.upper()
    repo = context.bot_data["parcel_repo"]
    created = await repo.create(
        Parcel(tracking_number=tn, user_id=update.effective_user.id, name=name)
    )
    if created is None:
        await update.message.reply_text(messages.parcel_duplicate(tn), parse_mode="HTML")
        return
    from parcel_tracker.bot.keyboards import name_prompt_keyboard, undo_keyboard  # noqa: PLC0415

    if name is None:
        if context.user_data is not None:
            context.user_data["pending"] = {"action": "name", "tn": tn}
        await update.message.reply_text(
            messages.parcel_added_auto(tn) + "\n\n" + messages.ask_parcel_name(),
            parse_mode="HTML",
            reply_markup=name_prompt_keyboard(tn, include_undo=True),
        )
        return
    await update.message.reply_text(
        messages.parcel_added_auto(tn), parse_mode="HTML", reply_markup=undo_keyboard(tn)
    )
