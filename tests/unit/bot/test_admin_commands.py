"""Smoke tests for admin_commands."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from parcel_tracker.bot.admin_commands import (
    cmd_clean,
    cmd_cleanall,
    cmd_delivered,
    cmd_stats,
)


def _make_update(user_id: int = 1) -> MagicMock:
    update = MagicMock()
    update.message = MagicMock()
    update.message.reply_text = AsyncMock()
    # PTB convention: effective_message mirrors message for command updates.
    update.effective_message = update.message
    update.effective_user = MagicMock()
    update.effective_user.id = user_id
    return update


def _make_context(
    *,
    owner_id: int = 1,
    parcel_repo: MagicMock | None = None,
    user_repo: MagicMock | None = None,
) -> MagicMock:
    context = MagicMock()
    config = MagicMock()
    config.owner_id = owner_id
    context.bot_data = {
        "config": config,
        "parcel_repo": parcel_repo or MagicMock(),
        "user_repo": user_repo or MagicMock(),
    }
    return context


@pytest.mark.asyncio
async def test_cmd_clean_owner_only() -> None:
    update = _make_update(user_id=99)
    context = _make_context(owner_id=1)
    await cmd_clean(update, context)
    text = update.message.reply_text.call_args.args[0]
    assert "owner" in text.lower()


@pytest.mark.asyncio
async def test_cmd_clean_owner_runs() -> None:
    update = _make_update(user_id=1)
    context = _make_context(owner_id=1)
    await cmd_clean(update, context)
    text = update.message.reply_text.call_args.args[0]
    assert "Cleanup complete" in text


@pytest.mark.asyncio
async def test_cmd_cleanall_owner_runs() -> None:
    update = _make_update(user_id=1)
    context = _make_context(owner_id=1)
    await cmd_cleanall(update, context)
    text = update.message.reply_text.call_args.args[0]
    assert "removed" in text.lower()


@pytest.mark.asyncio
async def test_cmd_delivered_no_delivered_replies_empty() -> None:
    update = _make_update(user_id=1)
    parcel_repo = MagicMock(list_active_for_user=AsyncMock(return_value=[]))
    context = _make_context(owner_id=1, parcel_repo=parcel_repo)
    await cmd_delivered(update, context)
    text = update.message.reply_text.call_args.args[0]
    assert "no delivered parcels" in text.lower()


@pytest.mark.asyncio
async def test_cmd_stats_owner_shows_count() -> None:
    update = _make_update(user_id=1)
    user_repo = MagicMock(get_allowed_user_ids=AsyncMock(return_value=[1, 2, 3]))
    context = _make_context(owner_id=1, user_repo=user_repo)
    await cmd_stats(update, context)
    text = update.message.reply_text.call_args.args[0]
    assert "3" in text
