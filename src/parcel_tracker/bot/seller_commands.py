"""Telegram side of the seller features: web dashboard link, CSV, share links,
shipment details and seller mode."""

from __future__ import annotations

import io
import logging
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, LinkPreviewOptions

from parcel_tracker.bot import messages
from parcel_tracker.bot.pending import set_pending
from parcel_tracker.core.csv_io import MAX_IMPORT_BYTES, CsvImportError, export_csv, import_csv
from parcel_tracker.core.shipments import clean_tags, clip_field, share_token_for
from parcel_tracker.i18n import _

if TYPE_CHECKING:
    from telegram import Message, Update
    from telegram.ext import ContextTypes

logger = logging.getLogger(__name__)

# Seller fields editable from the bot (callback data "detail:<field>:<code>").
DETAIL_FIELDS: tuple[str, ...] = ("order_ref", "recipient", "destination", "notes", "tags")
_CLEAR = "-"
_NO_PREVIEW = LinkPreviewOptions(is_disabled=True)


def _field_label(field: str) -> str:
    return {
        "order_ref": _("Order reference"),
        "recipient": _("Customer"),
        "destination": _("Destination"),
        "notes": _("Notes"),
        "tags": _("Tags"),
    }.get(field, field)


def _web_config(context: ContextTypes.DEFAULT_TYPE) -> Any | None:
    config = context.bot_data.get("config")
    return config if getattr(config, "web_enabled", False) else None


# --- /web --------------------------------------------------------------------


async def cmd_web(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Send a one-time sign-in link for the web dashboard."""
    user = update.effective_user
    reply_to = update.effective_message
    if user is None or reply_to is None:
        return
    config = _web_config(context)
    web_repo = context.bot_data.get("web_repo")
    if config is None or web_repo is None:
        await reply_to.reply_text(messages.web_disabled(), parse_mode="HTML")
        return
    token = await web_repo.create_login_token(user.id)
    url = f"{config.web_public_url}/login?t={token}"
    await reply_to.reply_text(
        messages.web_login_link(url),
        parse_mode="HTML",
        link_preview_options=_NO_PREVIEW,
    )


# --- CSV ----------------------------------------------------------------------


async def cmd_export(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Send all the user's shipments as a CSV file."""
    user = update.effective_user
    reply_to = update.effective_message
    if user is None or reply_to is None:
        return
    parcels = await context.bot_data["parcel_repo"].list_all_for_user(user_id=user.id)
    if not parcels:
        await reply_to.reply_text(messages.no_parcels_active(), parse_mode="HTML")
        return
    data = export_csv(parcels).encode("utf-8-sig")
    stamp = datetime.now(UTC).strftime("%Y%m%d")
    await reply_to.reply_document(
        document=io.BytesIO(data),
        filename=f"shipments-{stamp}.csv",
        caption=messages.export_caption(len(parcels)),
        parse_mode="HTML",
    )


async def handle_csv_document(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """A .csv sent to the bot is imported as shipments."""
    user = update.effective_user
    message = update.message
    if user is None or message is None or message.document is None:
        return
    document = message.document
    if document.file_size is not None and document.file_size > MAX_IMPORT_BYTES:
        await message.reply_text(messages.import_too_large(), parse_mode="HTML")
        return
    telegram_file = await document.get_file()
    data = bytes(await telegram_file.download_as_bytearray())
    config = context.bot_data.get("config")
    try:
        report = await import_csv(
            context.bot_data["parcel_repo"],
            user_id=user.id,
            data=data,
            max_active=int(getattr(config, "max_active_shipments", 0) or 0),
        )
    except CsvImportError:
        await message.reply_text(messages.import_unreadable(), parse_mode="HTML")
        return
    await message.reply_text(
        messages.import_report(
            added=report.added,
            duplicates=report.duplicates,
            invalid=report.invalid,
            over_limit=report.over_limit,
            first_errors=report.errors[:5],
        ),
        parse_mode="HTML",
    )


# --- share link -------------------------------------------------------------------


async def share_parcel(
    update: Update, context: ContextTypes.DEFAULT_TYPE, tracking_number: str
) -> None:
    """Reply with the customer tracking link (created on first use)."""
    user = update.effective_user
    message = update.effective_message
    if user is None or message is None:
        return
    config = _web_config(context)
    if config is None:
        await message.reply_text(messages.web_disabled(), parse_mode="HTML")
        return
    repo = context.bot_data["parcel_repo"]
    parcel = await repo.get_for_user(tracking_number, user_id=user.id)
    if parcel is None:
        await message.reply_text(messages.parcel_not_found(tracking_number), parse_mode="HTML")
        return
    token = share_token_for(parcel)
    if parcel.share_token is None:
        await repo.set_share_token(tracking_number, user_id=user.id, token=token)
    await message.reply_text(
        messages.share_link(f"{config.web_public_url}/t/{token}"),
        parse_mode="HTML",
        link_preview_options=_NO_PREVIEW,
    )


# --- shipment details -------------------------------------------------------------


def details_keyboard(tracking_number: str) -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(_field_label(f), callback_data=f"detail:{f}:{tracking_number}")]
        for f in DETAIL_FIELDS
    ]
    rows.append([InlineKeyboardButton(_("⬅️ Back"), callback_data=f"parcel:open:{tracking_number}")])
    return InlineKeyboardMarkup(rows)


async def show_details_menu(
    update: Update, context: ContextTypes.DEFAULT_TYPE, tracking_number: str
) -> None:
    query = update.callback_query
    user = update.effective_user
    if query is None or user is None:
        return
    parcel = await context.bot_data["parcel_repo"].get_for_user(tracking_number, user_id=user.id)
    if parcel is None:
        await query.edit_message_text(messages.parcel_not_found(tracking_number), parse_mode="HTML")
        return
    await query.edit_message_text(
        messages.details_menu(parcel),
        parse_mode="HTML",
        reply_markup=details_keyboard(tracking_number),
    )


async def ask_detail(
    update: Update, context: ContextTypes.DEFAULT_TYPE, field: str, tracking_number: str
) -> None:
    query = update.callback_query
    if query is None or field not in DETAIL_FIELDS:
        return
    set_pending(context, "detail", tn=tracking_number, field=field)
    await query.edit_message_text(
        messages.ask_detail_value(_field_label(field), tracking_number), parse_mode="HTML"
    )


async def consume_detail(
    pending: dict[str, Any],
    text: str,
    reply_to: Message,
    context: ContextTypes.DEFAULT_TYPE,
    user_id: int,
) -> None:
    """Store the text sent after "send the new value"; '-' clears the field."""
    field = str(pending.get("field", ""))
    tracking_number = str(pending.get("tn", ""))
    if field not in DETAIL_FIELDS:
        return
    raw = text.strip()
    value: str | list[str] | None
    if field == "tags":
        value = [] if raw == _CLEAR else clean_tags(raw)
    else:
        value = None if raw == _CLEAR else clip_field(field, raw)
    repo = context.bot_data["parcel_repo"]
    ok = await repo.update_details(tracking_number, user_id=user_id, **{field: value})
    if not ok:
        await reply_to.reply_text(messages.parcel_not_found(tracking_number), parse_mode="HTML")
        return
    from parcel_tracker.bot.keyboards import parcel_actions_keyboard  # noqa: PLC0415

    parcel = await repo.get_for_user(tracking_number, user_id=user_id)
    await reply_to.reply_text(
        messages.detail_saved(_field_label(field)) + "\n\n" + messages.parcel_detail_card(parcel),
        parse_mode="HTML",
        reply_markup=parcel_actions_keyboard(tracking_number),
    )


# --- seller mode ----------------------------------------------------------------


async def toggle_seller_mode(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    user = update.effective_user
    settings = context.bot_data.get("settings")
    if query is None or user is None or settings is None:
        return
    enabled = not await settings.seller_mode(user.id)
    await settings.set_seller_mode(user.id, enabled)
    from parcel_tracker.bot.keyboards import settings_submenu  # noqa: PLC0415

    await query.edit_message_text(
        messages.seller_mode_changed(enabled),
        parse_mode="HTML",
        reply_markup=settings_submenu(seller_mode=enabled),
    )
