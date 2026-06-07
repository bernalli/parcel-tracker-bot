from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from parcel_tracker.bot import callbacks
from parcel_tracker.db.models import Parcel, ShipmentStatus


def _cb_update(data: str, user_id: int = 10) -> SimpleNamespace:
    query = SimpleNamespace(
        data=data,
        answer=AsyncMock(),
        edit_message_text=AsyncMock(),
        from_user=SimpleNamespace(id=user_id),
    )
    return SimpleNamespace(
        callback_query=query,
        effective_user=SimpleNamespace(id=user_id),
    )


def _parcel() -> Parcel:
    return Parcel(tracking_number="TN1", user_id=10, name="iPhone", status=ShipmentStatus.IN_TRANSIT)


@pytest.mark.asyncio
async def test_refresh_fetches_live_and_edits_card() -> None:
    repo = AsyncMock()
    repo.get_for_user.return_value = _parcel()
    update = _cb_update("parcel:refresh:TN1")
    context = SimpleNamespace(bot_data={"parcel_repo": repo}, user_data={})
    with patch.object(callbacks, "check_parcel_now", new=AsyncMock(return_value="updated")) as chk:
        await callbacks.handle_callback(update, context)  # type: ignore[arg-type]
    chk.assert_awaited_once_with(context.bot_data, user_id=10, tracking_number="TN1")
    # _edit passes the text as first positional arg of edit_message_text
    text = update.callback_query.edit_message_text.await_args.args[0]
    assert "iPhone" in text


@pytest.mark.asyncio
async def test_refresh_quarantined_prefixes_notice() -> None:
    repo = AsyncMock()
    repo.get_for_user.return_value = _parcel()
    update = _cb_update("parcel:refresh:TN1")
    context = SimpleNamespace(bot_data={"parcel_repo": repo}, user_data={})
    with patch.object(callbacks, "check_parcel_now", new=AsyncMock(return_value="quarantined")):
        await callbacks.handle_callback(update, context)  # type: ignore[arg-type]
    text = update.callback_query.edit_message_text.await_args.args[0]
    assert "⏳" in text          # avviso quarantena
    assert "iPhone" in text      # card dal DB comunque mostrata


@pytest.mark.asyncio
async def test_refresh_in_flight_guard_skips_second_tap() -> None:
    repo = AsyncMock()
    repo.get_for_user.return_value = _parcel()
    update = _cb_update("parcel:refresh:TN1")
    context = SimpleNamespace(bot_data={"parcel_repo": repo}, user_data={})
    callbacks._REFRESH_IN_FLIGHT.add("TN1")
    try:
        with patch.object(callbacks, "check_parcel_now", new=AsyncMock()) as chk:
            await callbacks.handle_callback(update, context)  # type: ignore[arg-type]
        chk.assert_not_awaited()
    finally:
        callbacks._REFRESH_IN_FLIGHT.discard("TN1")


@pytest.mark.asyncio
async def test_refresh_foreign_parcel_not_found() -> None:
    repo = AsyncMock()
    repo.get_for_user.return_value = None
    update = _cb_update("parcel:refresh:TN1")
    context = SimpleNamespace(bot_data={"parcel_repo": repo}, user_data={})
    with patch.object(callbacks, "check_parcel_now", new=AsyncMock(return_value=None)):
        await callbacks.handle_callback(update, context)  # type: ignore[arg-type]
    text = update.callback_query.edit_message_text.await_args.args[0]
    assert "not found" in text.lower() or "❌" in text
