"""Inline callback query dispatcher."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from telegram import Update
    from telegram.ext import ContextTypes

logger = logging.getLogger(__name__)


async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Dispatch inline keyboard callbacks based on callback_data prefix.

    Will route to specific handlers (list / add / checkall / refresh / events / remove).
    For now: ack the callback and edit the message with the action received.
    """
    query = update.callback_query
    if query is None:
        return
    await query.answer()
    data = query.data or ""
    logger.debug("Callback received: %s", data)

    action, _, _payload = data.partition(":")
    text = f"Action: {action}" if action else "Action: (empty)"
    await query.edit_message_text(text)
