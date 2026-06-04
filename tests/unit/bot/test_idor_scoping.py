from unittest.mock import AsyncMock, MagicMock

import pytest

from parcel_tracker.bot.parcel_commands import cmd_remove, cmd_status


def _update(uid: int) -> MagicMock:
    update = MagicMock()
    update.effective_user = MagicMock(id=uid)
    update.effective_message = MagicMock()
    update.effective_message.reply_text = AsyncMock()
    return update


@pytest.mark.asyncio
async def test_cmd_status_not_owned_replies_not_found() -> None:
    repo = MagicMock()
    repo.get_for_user = AsyncMock(return_value=None)  # not owned by caller
    update = _update(7)
    context = MagicMock()
    context.args = ["TN1"]
    context.bot_data = {"parcel_repo": repo}
    await cmd_status(update, context)
    repo.get_for_user.assert_awaited_once_with("TN1", user_id=7)
    out = update.effective_message.reply_text.await_args.args[0]
    assert "not found" in out.lower() or "non" in out.lower()


@pytest.mark.asyncio
async def test_cmd_remove_not_owned_does_not_deactivate() -> None:
    repo = MagicMock()
    repo.get_for_user = AsyncMock(return_value=None)
    repo.deactivate = AsyncMock()
    update = _update(7)
    context = MagicMock()
    context.args = ["TN1"]
    context.bot_data = {"parcel_repo": repo}
    await cmd_remove(update, context)
    repo.deactivate.assert_not_awaited()
