"""Inline callback query dispatcher.

Routes callback_data of the form:

    nav:<section>          → navigate to a menu section
    action:<name>          → invoke a command (cmd_list / cmd_help / ...)
    prompt:<name>          → show a usage prompt for a text-arg command
    parcel:<action>:<tn>   → per-parcel action (refresh / events / remove)
    confirm:<action>:<tn>  → delivery-confirmation action (yes / no / undo)

Telegram catch-all is constrained at registration time (handlers.py) to those
five prefixes via a regex pattern so that other prefix-specific callbacks
(notify:*) are not shadowed.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from telegram import InlineKeyboardButton, InlineKeyboardMarkup

from parcel_tracker.bot import messages

# These cmd_* are imported for module-namespace lookup via _get_action_handler /
# _get_parcel_handler (resolved with getattr at dispatch time). They are not
# referenced directly in this module's body; the noqa suppresses ruff's F401.
from parcel_tracker.bot.admin_commands import (
    cmd_clean,  # noqa: F401  (lazy lookup target)
    cmd_delivered,  # noqa: F401  (lazy lookup target)
    cmd_stats,  # noqa: F401  (lazy lookup target)
)
from parcel_tracker.bot.auth_commands import cmd_users  # noqa: F401  (lazy lookup target)
from parcel_tracker.bot.keyboards import (
    admin_submenu,
    advanced_submenu,
    main_menu,
    parcels_submenu,
    settings_submenu,
)
from parcel_tracker.bot.lang_command import cmd_lang  # noqa: F401  (lazy lookup target)
from parcel_tracker.bot.navigation_commands import (
    cmd_help,  # noqa: F401  (lazy lookup target)
    cmd_map,  # noqa: F401  (lazy lookup target)
)
from parcel_tracker.bot.notify_commands import (
    cmd_notify_dispatch,  # noqa: F401  (lazy lookup target)
)
from parcel_tracker.bot.parcel_commands import (
    cmd_checkall,  # noqa: F401  (lazy lookup target)
    cmd_events,  # noqa: F401  (lazy lookup target)
    cmd_list,  # noqa: F401  (lazy lookup target)
    cmd_remove,  # noqa: F401  (lazy lookup target)
    cmd_status,  # noqa: F401  (lazy lookup target)
)
from parcel_tracker.i18n import _

if TYPE_CHECKING:
    from telegram import Update
    from telegram.ext import ContextTypes

logger = logging.getLogger(__name__)


def _back_only_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[InlineKeyboardButton(_("⬅️ Back"), callback_data="nav:main")]])


def _is_admin(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    config = context.bot_data.get("config")
    user = update.effective_user
    if config is None or user is None:
        return False
    admin_ids: frozenset[int] = getattr(config, "admin_user_ids", frozenset())
    try:
        return user.id in admin_ids
    except TypeError:
        return False


async def _edit(query: Any, text: str, reply_markup: InlineKeyboardMarkup | None) -> None:
    """Edit the callback message; tolerate Telegram 'message is not modified' errors."""
    try:
        await query.edit_message_text(text, reply_markup=reply_markup, parse_mode="HTML")
    except Exception:  # noqa: BLE001 — tolerate any edit failure (e.g. message unchanged)
        logger.exception("Failed to edit callback message")


# --- nav:* handlers --------------------------------------------------------


async def _nav_main(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if query is None:
        return
    is_admin = _is_admin(update, context)
    await _edit(query, messages.menu_header(), main_menu(is_admin=is_admin))


async def _nav_parcels(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if query is None:
        return
    await _edit(query, messages.menu_section_parcels(), parcels_submenu())


async def _nav_settings(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if query is None:
        return
    await _edit(query, messages.menu_section_settings(), settings_submenu())


async def _nav_advanced(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if query is None:
        return
    await _edit(query, messages.menu_section_advanced(), advanced_submenu())


async def _nav_admin(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if query is None:
        return
    if not _is_admin(update, context):
        await _edit(query, messages.unauthorized(), _back_only_keyboard())
        return
    await _edit(query, messages.menu_section_admin(), admin_submenu())


# --- action:* handlers -----------------------------------------------------


async def _action_lang(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    context.args = []
    await cmd_lang(update, context)


async def _action_health(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    # Local import to avoid circular dep at module import time.
    from parcel_tracker.bot.health_commands import cmd_health  # noqa: PLC0415

    context.args = []
    await cmd_health(update, context)


async def _action_notify(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    context.args = []
    await cmd_notify_dispatch(update, context)


async def _admin_gate(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    """Return True iff caller is admin; otherwise reply with unauthorised."""
    if _is_admin(update, context):
        return True
    query = update.callback_query
    if query is not None:
        await _edit(query, messages.unauthorized(), _back_only_keyboard())
    return False


async def _action_users(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await _admin_gate(update, context):
        return
    await cmd_users(update, context)


async def _action_stats(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await _admin_gate(update, context):
        return
    await cmd_stats(update, context)


async def _action_delivered(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await _admin_gate(update, context):
        return
    await cmd_delivered(update, context)


async def _action_clean(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await _admin_gate(update, context):
        return
    await cmd_clean(update, context)


def _get_action_handler(name: str):  # type: ignore[no-untyped-def]
    """Resolve an action name to its handler at dispatch time.

    Resolved lazily through this module's namespace so tests can patch
    the cmd_* references via patch.object(callbacks, ...).
    """
    # Mapping of action name → attribute name in this module.
    table = {
        "list": "cmd_list",
        "checkall": "cmd_checkall",
        "help": "cmd_help",
        "map": "cmd_map",
        "health": "_action_health",
        "notify": "_action_notify",
        "lang": "_action_lang",
        "users": "_action_users",
        "stats": "_action_stats",
        "delivered": "_action_delivered",
        "clean": "_action_clean",
    }
    attr = table.get(name)
    if attr is None:
        return None
    import sys  # noqa: PLC0415

    return getattr(sys.modules[__name__], attr, None)


# --- prompt:* handlers -----------------------------------------------------


_PROMPT_TEXTS: dict[str, object] = {
    "add": messages.prompt_add,
    "status": messages.prompt_status,
    "events": messages.prompt_events,
    "rename": messages.prompt_rename,
    "remove": messages.prompt_remove,
}


async def _handle_prompt(update: Update, context: ContextTypes.DEFAULT_TYPE, name: str) -> None:
    query = update.callback_query
    if query is None:
        return
    fn = _PROMPT_TEXTS.get(name)
    if fn is None:
        logger.debug("Unknown prompt: %s", name)
        await _edit(query, messages.menu_header(), main_menu(is_admin=_is_admin(update, context)))
        return
    text = fn()  # type: ignore[operator]
    await _edit(query, text, _back_only_keyboard())


# --- parcel:<action>:<tn> handlers -----------------------------------------


def _get_parcel_handler(action: str):  # type: ignore[no-untyped-def]
    """Resolve parcel:<action>:<tn> action to its cmd_* handler.

    Looked up lazily through the module namespace so tests can patch
    the cmd_* references via patch.object(callbacks, ...).
    """
    table = {
        "refresh": "cmd_status",
        "events": "cmd_events",
        "remove": "cmd_remove",
    }
    attr = table.get(action)
    if attr is None:
        return None
    import sys  # noqa: PLC0415

    return getattr(sys.modules[__name__], attr, None)


async def _handle_parcel(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    action: str,
    tracking_number: str,
) -> None:
    handler = _get_parcel_handler(action)
    if handler is None:
        logger.debug("Unknown parcel action: %s", action)
        return
    context.args = [tracking_number]
    await handler(update, context)


# --- main dispatcher -------------------------------------------------------


_NAV_HANDLERS = {
    "main": _nav_main,
    "parcels": _nav_parcels,
    "settings": _nav_settings,
    "advanced": _nav_advanced,
    "admin": _nav_admin,
}


async def _dispatch_nav(
    update: Update, context: ContextTypes.DEFAULT_TYPE, parts: list[str]
) -> None:
    section = parts[1] if len(parts) >= 2 else "main"
    handler = _NAV_HANDLERS.get(section)
    if handler is None:
        logger.debug("Unknown nav section: %s", section)
        return
    await handler(update, context)


async def _dispatch_action(
    update: Update, context: ContextTypes.DEFAULT_TYPE, parts: list[str]
) -> None:
    name = parts[1] if len(parts) >= 2 else ""
    handler = _get_action_handler(name)
    if handler is None:
        logger.debug("Unknown action: %s", name)
        return
    await handler(update, context)


async def _dispatch_prompt(
    update: Update, context: ContextTypes.DEFAULT_TYPE, parts: list[str]
) -> None:
    name = parts[1] if len(parts) >= 2 else ""
    await _handle_prompt(update, context, name)


async def _dispatch_parcel(
    update: Update, context: ContextTypes.DEFAULT_TYPE, parts: list[str]
) -> None:
    if len(parts) < 3:
        logger.debug("Malformed parcel callback: %s", ":".join(parts))
        return
    await _handle_parcel(update, context, parts[1], parts[2])


async def _dispatch_confirm(
    update: Update, context: ContextTypes.DEFAULT_TYPE, parts: list[str]
) -> None:
    if len(parts) < 3:
        return
    action, tracking_number = parts[1], parts[2]
    repo = context.bot_data["parcel_repo"]
    query = update.callback_query
    if query is None:
        return
    # Defense-in-depth: ownership check before any write.
    user_id = query.from_user.id
    parcel = await repo.get_for_user(tracking_number, user_id=user_id)
    if parcel is None:
        await _edit(query, messages.parcel_not_found(tracking_number), None)
        return
    if action == "yes":
        from datetime import UTC, datetime  # noqa: PLC0415

        await repo.set_delivered(tracking_number, datetime.now(UTC))
        await repo.deactivate(tracking_number)
        await _edit(query, messages.delivered_archived(tracking_number), None)
    elif action == "no":
        await repo.set_disputed(tracking_number, True)
        await repo.reactivate(tracking_number)
        await _edit(query, messages.delivery_kept_tracking(tracking_number), None)
    elif action == "undo":
        await repo.deactivate(tracking_number)
        await _edit(query, messages.parcel_undone(tracking_number), None)


_PREFIX_DISPATCH = {
    "nav": _dispatch_nav,
    "action": _dispatch_action,
    "prompt": _dispatch_prompt,
    "parcel": _dispatch_parcel,
    "confirm": _dispatch_confirm,
}


async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Dispatch inline keyboard callbacks based on callback_data prefix."""
    query = update.callback_query
    if query is None:
        return
    await query.answer()
    data = query.data or ""
    logger.debug("Callback received: %s", data)

    parts = data.split(":", 2)
    prefix = parts[0] if parts else ""
    dispatcher = _PREFIX_DISPATCH.get(prefix)
    if dispatcher is None:
        logger.debug("Unknown callback prefix: %s", prefix)
        return
    await dispatcher(update, context, parts)
