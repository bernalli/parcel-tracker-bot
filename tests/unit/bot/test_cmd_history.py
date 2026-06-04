from unittest.mock import AsyncMock, MagicMock

import pytest

from parcel_tracker.bot.parcel_commands import cmd_history
from parcel_tracker.db.models import Parcel, ShipmentStatus


@pytest.mark.asyncio
async def test_cmd_history_lists_archived() -> None:
    repo = MagicMock()
    repo.list_archived_for_user = AsyncMock(
        return_value=[
            Parcel(tracking_number="TN1", user_id=7, name="amz", status=ShipmentStatus.DELIVERED)
        ]
    )
    update = MagicMock()
    update.effective_user = MagicMock(id=7)
    update.effective_message = MagicMock()
    update.effective_message.reply_text = AsyncMock()
    context = MagicMock()
    context.bot_data = {"parcel_repo": repo}
    await cmd_history(update, context)
    out = update.effective_message.reply_text.await_args.args[0]
    assert "TN1" in out


@pytest.mark.asyncio
async def test_cmd_history_empty() -> None:
    repo = MagicMock()
    repo.list_archived_for_user = AsyncMock(return_value=[])
    update = MagicMock()
    update.effective_user = MagicMock(id=7)
    update.effective_message = MagicMock()
    update.effective_message.reply_text = AsyncMock()
    context = MagicMock()
    context.bot_data = {"parcel_repo": repo}
    await cmd_history(update, context)
    update.effective_message.reply_text.assert_awaited_once()
