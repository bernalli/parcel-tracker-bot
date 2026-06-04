from unittest.mock import AsyncMock, MagicMock

import pytest

from parcel_tracker.bot.callbacks import handle_callback
from parcel_tracker.db.models import Parcel, ShipmentStatus


def _q(data: str, uid: int = 7) -> MagicMock:
    q = MagicMock()
    q.data = data
    q.answer = AsyncMock()
    q.edit_message_text = AsyncMock()
    q.from_user = MagicMock(id=uid)
    return q


def _owned_parcel() -> Parcel:
    return Parcel(tracking_number="TN1", user_id=7, status=ShipmentStatus.IN_TRANSIT)


@pytest.mark.asyncio
async def test_confirm_yes_archives() -> None:
    repo = MagicMock()
    repo.get_for_user = AsyncMock(return_value=_owned_parcel())
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
    repo.get_for_user = AsyncMock(return_value=_owned_parcel())
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
    repo.get_for_user = AsyncMock(return_value=_owned_parcel())
    repo.deactivate = AsyncMock()
    update = MagicMock()
    update.callback_query = _q("confirm:undo:TN1")
    context = MagicMock()
    context.bot_data = {"parcel_repo": repo, "config": MagicMock(admin_user_ids=frozenset())}
    await handle_callback(update, context)
    repo.deactivate.assert_awaited_once_with("TN1")
