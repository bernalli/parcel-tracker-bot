"""Regression test: bot must not swallow unexpected exceptions silently (Bug #2)."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest


@pytest.mark.asyncio
async def test_cmd_status_propagates_unexpected_exception() -> None:
    from parcel_tracker.bot.parcel_commands import cmd_status

    update = MagicMock()
    update.effective_user.id = 1
    update.message.reply_text = AsyncMock()
    update.effective_message = update.message
    update.effective_chat.id = 1
    context = MagicMock()
    context.args = ["XYZ"]
    context.bot_data = {
        "parcel_repo": MagicMock(get_for_user=AsyncMock(side_effect=RuntimeError("unexpected")))
    }

    with pytest.raises(RuntimeError, match="unexpected"):
        await cmd_status(update, context)
