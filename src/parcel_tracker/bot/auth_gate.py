"""Central authorization gate: runs before every handler and drops unauthorised updates.

Registered as a ``TypeHandler`` in a negative group so it sees each update first.
An update from a user who is not the owner, an admin, on the env allow-list
(``ALLOWED_USER_IDS``) or in the ``allowed_users`` table is answered once with the
"not authorised" text and then stopped with ``ApplicationHandlerStop``, so no
command, message or callback handler (including those registered in ``main.py``)
ever runs for it. ``/whoami`` stays public so a stranger can tell the owner which
ID to authorise.
"""

from __future__ import annotations

import logging
from typing import Any

from telegram import Update
from telegram.ext import ApplicationHandlerStop, ContextTypes

from parcel_tracker.bot import messages

logger = logging.getLogger(__name__)

# Group for the gate's TypeHandler: lower groups run first in python-telegram-bot.
AUTH_GATE_GROUP = -1

_PUBLIC_COMMANDS = frozenset({"whoami"})


async def is_authorized(context: Any, user_id: int) -> bool:
    """True iff ``user_id`` is the owner, an admin, env-allowed or in allowed_users."""
    config = context.bot_data.get("config")
    if config is not None:
        if getattr(config, "owner_id", None) == user_id:
            return True
        if user_id in (getattr(config, "allowed_user_ids", ()) or ()):
            return True
        if user_id in (getattr(config, "admin_user_ids", ()) or ()):
            return True
    user_repo = context.bot_data.get("user_repo")
    if user_repo is None:
        return False
    return user_id in await user_repo.get_allowed_user_ids()


def _command_name(update: Update) -> str | None:
    """Return the bare command (``/whoami@MyBot args`` → ``whoami``), or None."""
    message = update.message
    if message is None or not message.text or not message.text.startswith("/"):
        return None
    return message.text.split(maxsplit=1)[0][1:].split("@", 1)[0].lower()


async def authorization_gate(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Let authorised updates through; reply once to and stop everything else."""
    if not isinstance(update, Update):
        raise ApplicationHandlerStop
    user = update.effective_user
    if user is not None and await is_authorized(context, user.id):
        return
    if _command_name(update) in _PUBLIC_COMMANDS:
        return

    if user is not None:
        logger.info("Rejected update from unauthorised user %s", user.id)
        if update.callback_query is not None:
            await update.callback_query.answer(messages.unauthorized(), show_alert=True)
        elif update.message is not None:
            await update.message.reply_text(messages.unauthorized(), parse_mode="HTML")
    raise ApplicationHandlerStop
