"""Tests for /notify command family."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from parcel_tracker.bot.notify_commands import (
    cmd_notify,
    cmd_notify_dispatch,
    on_notify_callback,
)
from parcel_tracker.db.models import ShipmentStatus


@pytest.mark.asyncio
async def test_cmd_notify_displays_menu_with_all_status() -> None:
    notification_repo = MagicMock()
    notification_repo.get_all_prefs = AsyncMock(return_value={})

    update = MagicMock()
    update.effective_user.id = 1
    update.message.reply_text = AsyncMock()
    context = MagicMock()
    context.bot_data = {"notification_repo": notification_repo}

    await cmd_notify(update, context)

    update.message.reply_text.assert_awaited_once()
    args, kwargs = update.message.reply_text.call_args
    text = args[0]
    assert "notify" in text.lower() or "notification" in text.lower()
    keyboard = kwargs["reply_markup"].inline_keyboard
    flat_buttons = [b for row in keyboard for b in row]
    expected_count = len(ShipmentStatus) - 1
    status_buttons = [
        b for b in flat_buttons if b.callback_data and b.callback_data.startswith("notify:")
    ]
    assert len(status_buttons) == expected_count


@pytest.mark.asyncio
async def test_cmd_notify_dispatch_on_quick_command_all() -> None:
    notification_repo = MagicMock()
    notification_repo.set_pref = AsyncMock()

    update = MagicMock()
    update.effective_user.id = 1
    update.message.reply_text = AsyncMock()
    context = MagicMock()
    context.args = ["all"]
    context.bot_data = {"notification_repo": notification_repo}

    await cmd_notify_dispatch(update, context)

    assert notification_repo.set_pref.await_count == len(ShipmentStatus) - 1
    for call in notification_repo.set_pref.await_args_list:
        kwargs = call.kwargs
        assert kwargs["enabled"] is True


@pytest.mark.asyncio
async def test_cmd_notify_dispatch_on_quick_command_none() -> None:
    notification_repo = MagicMock()
    notification_repo.set_pref = AsyncMock()
    update = MagicMock()
    update.effective_user.id = 1
    update.message.reply_text = AsyncMock()
    context = MagicMock()
    context.args = ["none"]
    context.bot_data = {"notification_repo": notification_repo}

    await cmd_notify_dispatch(update, context)
    for call in notification_repo.set_pref.await_args_list:
        assert call.kwargs["enabled"] is False


@pytest.mark.asyncio
async def test_cmd_notify_dispatch_on_quick_command_on_specific() -> None:
    notification_repo = MagicMock()
    notification_repo.set_pref = AsyncMock()
    update = MagicMock()
    update.effective_user.id = 1
    update.message.reply_text = AsyncMock()
    context = MagicMock()
    context.args = ["on", "InTransit"]
    context.bot_data = {"notification_repo": notification_repo}

    await cmd_notify_dispatch(update, context)
    notification_repo.set_pref.assert_awaited_once_with(
        user_id=1, status_value="InTransit", enabled=True
    )


@pytest.mark.asyncio
async def test_cmd_notify_dispatch_unknown_status_returns_error() -> None:
    notification_repo = MagicMock()
    notification_repo.set_pref = AsyncMock()
    update = MagicMock()
    update.effective_user.id = 1
    update.message.reply_text = AsyncMock()
    context = MagicMock()
    context.args = ["on", "BogusStatus"]
    context.bot_data = {"notification_repo": notification_repo}

    await cmd_notify_dispatch(update, context)
    notification_repo.set_pref.assert_not_called()
    text = update.message.reply_text.call_args.args[0]
    assert "unknown" in text.lower()


@pytest.mark.asyncio
async def test_on_notify_callback_toggles_pref() -> None:
    notification_repo = MagicMock()
    notification_repo.get_pref = AsyncMock(return_value=False)
    notification_repo.get_all_prefs = AsyncMock(return_value={})
    notification_repo.set_pref = AsyncMock()

    update = MagicMock()
    update.callback_query.from_user.id = 1
    update.callback_query.data = "notify:Delivered"
    update.callback_query.answer = AsyncMock()
    update.callback_query.edit_message_text = AsyncMock()

    context = MagicMock()
    context.bot_data = {"notification_repo": notification_repo}

    await on_notify_callback(update, context)
    notification_repo.set_pref.assert_awaited_once_with(
        user_id=1, status_value="Delivered", enabled=True
    )
