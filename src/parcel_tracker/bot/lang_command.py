"""/lang command — show or change the user's UI language."""

from __future__ import annotations

from pathlib import Path

from telegram import Update
from telegram.ext import ContextTypes

from parcel_tracker.bot import messages
from parcel_tracker.db.repository import UserRepository
from parcel_tracker.i18n import (
    Translator,
    available_locales,
    set_default_translator,
)

LOCALE_ROOT = Path(__file__).resolve().parents[1] / "i18n" / "locale"


async def set_user_language(user_repo: UserRepository, user_id: int, locale: str) -> None:
    """Persist the user's locale and switch the active translator (shared by the
    /lang command and the inline language picker)."""
    await user_repo.set_language(user_id, locale)
    set_default_translator(Translator(locale=locale, locale_dir=LOCALE_ROOT))


async def cmd_lang(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    reply_to = update.effective_message
    if reply_to is None or update.effective_user is None:
        return
    user_id = update.effective_user.id
    user_repo: UserRepository = context.bot_data["user_repo"]
    args = context.args or []
    available = available_locales(LOCALE_ROOT)

    if not args:
        current = await user_repo.get_language(user_id)
        await reply_to.reply_text(
            messages.lang_current(current, available),
            parse_mode="HTML",
        )
        return

    requested = args[0].strip().lower()
    if requested not in available:
        await reply_to.reply_text(
            messages.lang_not_supported(requested, available),
            parse_mode="HTML",
        )
        return

    await set_user_language(user_repo, user_id, requested)
    await reply_to.reply_text(
        messages.lang_changed(requested),
        parse_mode="HTML",
    )
