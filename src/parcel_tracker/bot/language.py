"""Per-update UI language: every update is rendered in its sender's language."""

from __future__ import annotations

from typing import Any

from parcel_tracker.i18n import LOCALE_DIR, activate, available_locales, translator_for

# Runs right after the authorization gate (-2) and before every command handler
# (group 0), so unauthorised updates never reach it.
LANGUAGE_GROUP = -1


async def apply_user_language(update: object, context: Any) -> None:
    """Activate the sender's translator for the rest of this update's handlers.

    Always sets a value (the default translator when there is no user or no
    choice), so nothing carries over from a previous update.
    """
    user = getattr(update, "effective_user", None)
    user_repo = context.bot_data.get("user_repo")
    if user is None or user_repo is None:
        activate(None)
        return
    config = context.bot_data.get("config")
    default = getattr(config, "default_language", "en") or "en"
    locale = await user_repo.get_language(user.id, default=default)
    if locale not in available_locales(LOCALE_DIR):
        activate(None)
        return
    activate(translator_for(locale, LOCALE_DIR))
