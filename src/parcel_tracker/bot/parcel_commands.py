"""Parcel-related commands: add, list, status, events, remove, rename, checkall."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from parcel_tracker.bot import messages
from parcel_tracker.bot.pending import pop_pending, set_pending
from parcel_tracker.core.shipments import (
    FIELD_LIMITS,
    AddOutcome,
    ShipmentInput,
    add_shipment,
    clip_field,
    extract_code_and_name,
    is_known_code_format,
    is_valid_tracking_number,
    normalize_tracking_number,
    parse_bulk_codes,
    pick_single_code,
    s10_operator,
)
from parcel_tracker.db.models import Parcel

if TYPE_CHECKING:
    from telegram import Message, Update
    from telegram.ext import ContextTypes

logger = logging.getLogger(__name__)

_NAME_MAX_LEN = FIELD_LIMITS["name"]
# Echoed user text is clipped so a pasted wall of text cannot exceed Telegram's
# message limit (the reply would fail and the user would only see an error).
_ECHO_MAX_LEN = 40


def _code_arg(raw: str) -> str:
    """A tracking-code argument as stored: separators removed, upper-cased."""
    return normalize_tracking_number(raw)


def _echo(text: str) -> str:
    return text if len(text) <= _ECHO_MAX_LEN else text[: _ECHO_MAX_LEN - 1] + "…"


def _parcel_line(parcel: Parcel) -> str:
    """One-line label: bold name with code aside, or just the code when unnamed."""
    if parcel.name:
        return (
            f"<b>{messages.esc(parcel.name)}</b> — "
            f"<code>{messages.esc(parcel.tracking_number)}</code>"
        )
    return f"<code>{messages.esc(parcel.tracking_number)}</code>"


async def _active_limit_reached(context: ContextTypes.DEFAULT_TYPE, user_id: int) -> int | None:
    """Return the configured active-shipment cap when the user is at/over it, else None.

    No-op (None) when no config is present in bot_data, so the cap is enforced live
    (main.py always sets config) without coupling every command test to a Config stub.
    """
    config = context.bot_data.get("config")
    if config is None:
        return None
    limit = int(getattr(config, "max_active_shipments", 0) or 0)
    if limit <= 0:
        return None
    repo = context.bot_data["parcel_repo"]
    count = await repo.count_active_for_user(user_id=user_id)
    return limit if count >= limit else None


async def cmd_add(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Add a new parcel for the user. Args: tracking_number [name…] (multi-word name)."""
    user = update.effective_user
    if user is None or update.message is None:
        return
    args = context.args or []
    if not args:
        await update.message.reply_text(messages.add_usage(), parse_mode="HTML")
        return
    tracking_number = _code_arg(args[0])
    if not is_valid_tracking_number(tracking_number):
        await update.message.reply_text(messages.add_usage(), parse_mode="HTML")
        return
    name = clip_field("name", " ".join(args[1:]))

    limit = await _active_limit_reached(context, user.id)
    if limit is not None:
        await update.message.reply_text(messages.max_active_reached(limit), parse_mode="HTML")
        return

    repo = context.bot_data["parcel_repo"]
    parcel = Parcel(
        tracking_number=tracking_number,
        user_id=user.id,
        name=name,
        carrier_name=s10_operator(tracking_number),
    )
    created = await repo.create(parcel)
    if created is None:
        await update.message.reply_text(
            messages.parcel_duplicate(tracking_number), parse_mode="HTML"
        )
        return
    if name is None:
        from parcel_tracker.bot.keyboards import name_prompt_keyboard  # noqa: PLC0415

        set_pending(context, "name", tn=tracking_number)
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
    text = "\n".join(f"• {_parcel_line(p)}" for p in parcels)
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
    tracking_number = _code_arg(args[0])
    repo = context.bot_data["parcel_repo"]
    parcel = await repo.get_for_user(tracking_number, user_id=user.id)
    if parcel is None:
        await reply_to.reply_text(messages.parcel_not_found(tracking_number), parse_mode="HTML")
        return
    from parcel_tracker.bot.keyboards import parcel_actions_keyboard  # noqa: PLC0415

    await reply_to.reply_text(
        messages.parcel_detail_card(parcel),
        parse_mode="HTML",
        reply_markup=parcel_actions_keyboard(parcel.tracking_number),
    )


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
    tracking_number = _code_arg(args[0])
    repo = context.bot_data["parcel_repo"]
    parcel = await repo.get_for_user(tracking_number, user_id=user.id)
    if parcel is None:
        await reply_to.reply_text(messages.parcel_not_found(tracking_number), parse_mode="HTML")
        return
    events = await repo.get_history(tracking_number, limit=20, user_id=user.id)
    if not events:
        await reply_to.reply_text(messages.no_events(tracking_number), parse_mode="HTML")
        return
    from parcel_tracker.bot.formatting import fmt_event_time  # noqa: PLC0415

    lines = [messages.events_for(tracking_number)]
    for ev in events:
        when = fmt_event_time(ev.time)
        line = f"• <i>{messages.esc(when)}</i> — {messages.esc(ev.description)}"
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
    tracking_number = _code_arg(args[0])
    repo = context.bot_data["parcel_repo"]
    parcel = await repo.get_for_user(tracking_number, user_id=user.id)
    if parcel is None:
        await reply_to.reply_text(messages.parcel_not_found(tracking_number), parse_mode="HTML")
        return
    await repo.deactivate(tracking_number, user_id=user.id)
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
    tracking_number = _code_arg(args[0])
    new_name = " ".join(args[1:]).strip()[:_NAME_MAX_LEN]
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
    from parcel_tracker.bot import throttle  # noqa: PLC0415

    wait = throttle.CHECKALL.wait_seconds(user.id)
    if wait:
        await reply_to.reply_text(messages.try_again_in(wait), parse_mode="HTML")
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
        lines.append(f"✅ {_parcel_line(p)}")
    await reply_to.reply_text("\n".join(lines), parse_mode="HTML")


async def _consume_pending_name(
    pending: dict[str, str],
    text: str,
    reply_to: Message,
    context: ContextTypes.DEFAULT_TYPE,
    user_id: int,
) -> bool:
    """Use ``text`` as the name of a just-added parcel.

    Returns False when the reply is really another tracking code, so the caller
    adds it instead. Only a certain code format counts (a carrier pattern or a
    valid UPU S10): product names such as "AirPods2023" are names, not codes.
    """
    code, _rest = extract_code_and_name(text, context.bot_data.get("detector"))
    if is_known_code_format(code, context.bot_data.get("detector")):
        return False
    repo = context.bot_data["parcel_repo"]
    name = text.strip()[:_NAME_MAX_LEN]
    ok = await repo.rename(pending["tn"], user_id=user_id, name=name)
    msg = (
        messages.parcel_renamed(pending["tn"], name)
        if ok
        else messages.parcel_not_found(pending["tn"])
    )
    await reply_to.reply_text(msg, parse_mode="HTML")
    return True


async def _consume_user_id(
    action: str, text: str, reply_to: Message, context: ContextTypes.DEFAULT_TYPE, admin_id: int
) -> None:
    """Authorise or revoke the numeric Telegram user ID in ``text``."""
    usage = messages.adduser_usage() if action == "adduser" else messages.removeuser_usage()
    try:
        target = int(text.strip())
    except ValueError:
        await reply_to.reply_text(usage, parse_mode="HTML")
        return
    if action == "adduser":
        added = await context.bot_data["user_repo"].add_user(user_id=target, added_by=admin_id)
        await reply_to.reply_text(
            messages.user_added(target) if added else messages.user_duplicate(target),
            parse_mode="HTML",
        )
        return
    from parcel_tracker.bot.auth_commands import revoke_user  # noqa: PLC0415

    await reply_to.reply_text(await revoke_user(context, target), parse_mode="HTML")


async def _consume_pending(update: Update, context: ContextTypes.DEFAULT_TYPE, text: str) -> bool:
    """If a guided input is pending for this user, consume `text` as its value.
    Returns True if it handled the message."""
    user = update.effective_user
    reply_to = update.message
    if user is None or reply_to is None:
        return False
    pending = pop_pending(context)  # consumed once; expired prompts are dropped
    if not pending:
        return False
    action = pending.get("action")
    detector = context.bot_data.get("detector")
    if action == "name":
        return await _consume_pending_name(pending, text, reply_to, context, user.id)
    if action == "rename":
        code, _rest = extract_code_and_name(text, detector)
        if is_known_code_format(code, detector):
            return False  # a pasted code is a new parcel, not the new name
        name = text.strip()[:_NAME_MAX_LEN]
        repo = context.bot_data["parcel_repo"]
        ok = await repo.rename(pending["tn"], user_id=user.id, name=name)
        msg = (
            messages.parcel_renamed(pending["tn"], name)
            if ok
            else messages.parcel_not_found(pending["tn"])
        )
        await reply_to.reply_text(msg, parse_mode="HTML")
        return True
    if action in ("adduser", "revoke"):
        await _consume_user_id(action, text, reply_to, context, user.id)
        return True
    if action == "detail":
        from parcel_tracker.bot.seller_commands import consume_detail  # noqa: PLC0415

        await consume_detail(pending, text, reply_to, context, user.id)
        return True
    return False


async def _bulk_add(
    update: Update, context: ContextTypes.DEFAULT_TYPE, codes: list[tuple[str, str | None]]
) -> None:
    """Add every code of a multi-line paste and reply with one summary."""
    user = update.effective_user
    message = update.message
    if user is None or message is None:
        return
    config = context.bot_data.get("config")
    max_active = int(getattr(config, "max_active_shipments", 0) or 0)
    counts = dict.fromkeys(AddOutcome, 0)
    for code, name in codes:
        outcome, _parcel = await add_shipment(
            context.bot_data["parcel_repo"],
            user_id=user.id,
            data=ShipmentInput(tracking_number=code, name=name),
            max_active=max_active,
        )
        counts[outcome] += 1
    await message.reply_text(
        messages.bulk_added(
            added=counts[AddOutcome.ADDED],
            duplicates=counts[AddOutcome.DUPLICATE],
            over_limit=counts[AddOutcome.LIMIT],
        ),
        parse_mode="HTML",
    )


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Plain text → if it looks like a tracking number, auto-add it (no /add needed).

    A code printed with spaces ("1Z 999 AA1 …") is recognised as one code, a code
    inside a sentence or a carrier link is picked out, and a message with several
    codes (one per line, a numbered list, or comma-separated) adds them all.
    """
    if update.message is None or update.effective_user is None:
        return
    text = (update.message.text or "").strip()
    if not text:
        return
    if await _consume_pending(update, context, text):
        return
    detector = context.bot_data.get("detector")
    bulk = parse_bulk_codes(text, detector)
    if bulk:
        await _bulk_add(update, context, bulk)
        return
    picked = pick_single_code(text, detector)
    if picked is None:
        first_word = text.split()[0]
        await update.message.reply_text(messages.to_add_use(_echo(first_word)), parse_mode="HTML")
        return
    candidate, name = picked

    limit = await _active_limit_reached(context, update.effective_user.id)
    if limit is not None:
        await update.message.reply_text(messages.max_active_reached(limit), parse_mode="HTML")
        return

    name = clip_field("name", name)
    tn = candidate
    repo = context.bot_data["parcel_repo"]
    created = await repo.create(
        Parcel(
            tracking_number=tn,
            user_id=update.effective_user.id,
            name=name,
            carrier_name=s10_operator(tn),
        )
    )
    if created is None:
        await update.message.reply_text(messages.parcel_duplicate(tn), parse_mode="HTML")
        return
    from parcel_tracker.bot.keyboards import name_prompt_keyboard, undo_keyboard  # noqa: PLC0415

    if name is None:
        set_pending(context, "name", tn=tn)
        await update.message.reply_text(
            messages.parcel_added_auto(tn) + "\n\n" + messages.ask_parcel_name(),
            parse_mode="HTML",
            reply_markup=name_prompt_keyboard(tn, include_undo=True),
        )
        return
    await update.message.reply_text(
        messages.parcel_added_auto(tn), parse_mode="HTML", reply_markup=undo_keyboard(tn)
    )
