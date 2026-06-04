from unittest.mock import AsyncMock, MagicMock

import pytest

from parcel_tracker.bot.callbacks import handle_callback


def _q(data: str) -> MagicMock:
    q = MagicMock()
    q.data = data
    q.answer = AsyncMock()
    q.edit_message_text = AsyncMock()
    return q


@pytest.mark.asyncio
async def test_confirm_yes_archives() -> None:
    repo = MagicMock()
    repo.set_delivered = AsyncMock()
    repo.deactivate = AsyncMock()
    update = MagicMock()
    update.callback_query = _q("confirm:yes:TN1")
    context = MagicMock()
    context.bot_data = {"parcel_repo": repo, "config": MagicMock(admin_user_ids=frozenset())}
    await handle_callback(update, context)
    repo.deactivate.assert_awaited_once_with("TN1")


@pytest.mark.asyncio
async def test_confirm_no_keeps_tracking() -> None:
    repo = MagicMock()
    repo.set_disputed = AsyncMock()
    repo.reactivate = AsyncMock()
    update = MagicMock()
    update.callback_query = _q("confirm:no:TN1")
    context = MagicMock()
    context.bot_data = {"parcel_repo": repo, "config": MagicMock(admin_user_ids=frozenset())}
    await handle_callback(update, context)
    repo.set_disputed.assert_awaited_once_with("TN1", True)


@pytest.mark.asyncio
async def test_confirm_undo_removes() -> None:
    repo = MagicMock()
    repo.deactivate = AsyncMock()
    update = MagicMock()
    update.callback_query = _q("confirm:undo:TN1")
    context = MagicMock()
    context.bot_data = {"parcel_repo": repo, "config": MagicMock(admin_user_ids=frozenset())}
    await handle_callback(update, context)
    repo.deactivate.assert_awaited_once_with("TN1")
