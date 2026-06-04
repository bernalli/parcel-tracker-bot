from unittest.mock import AsyncMock, MagicMock

import pytest

from parcel_tracker.bot.parcel_commands import cmd_add


@pytest.mark.asyncio
async def test_cmd_add_duplicate_replies_gracefully() -> None:
    repo = MagicMock()
    repo.create = AsyncMock(return_value=None)  # duplicate
    update = MagicMock()
    update.effective_user = MagicMock(id=7)
    update.message = MagicMock()
    update.message.reply_text = AsyncMock()
    context = MagicMock()
    context.args = ["1Z999AA10123456784"]
    context.bot_data = {"parcel_repo": repo}
    await cmd_add(update, context)
    sent = update.message.reply_text.await_args.args[0]
    assert "already" in sent.lower() or "già" in sent.lower()
