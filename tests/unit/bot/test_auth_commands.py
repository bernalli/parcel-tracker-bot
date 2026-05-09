"""Smoke tests for auth_commands."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from parcel_tracker.bot.auth_commands import (
    cmd_adduser,
    cmd_removeuser,
    cmd_users,
    cmd_whoami,
)


def _make_update(user_id: int = 1, username: str | None = "alice") -> MagicMock:
    update = MagicMock()
    update.message = MagicMock()
    update.message.reply_text = AsyncMock()
    update.effective_user = MagicMock()
    update.effective_user.id = user_id
    update.effective_user.username = username
    return update


def _make_context(
    args: list[str] | None = None,
    *,
    owner_id: int = 1,
    user_repo: MagicMock | None = None,
) -> MagicMock:
    context = MagicMock()
    context.args = args or []
    config = MagicMock()
    config.owner_id = owner_id
    context.bot_data = {
        "config": config,
        "user_repo": user_repo or MagicMock(),
    }
    return context


@pytest.mark.asyncio
async def test_cmd_whoami_replies_with_id() -> None:
    update = _make_update(user_id=42, username="bob")
    context = _make_context()
    await cmd_whoami(update, context)
    update.message.reply_text.assert_called_once()
    text = update.message.reply_text.call_args.args[0]
    assert "42" in text
    assert "bob" in text


@pytest.mark.asyncio
async def test_cmd_adduser_owner_only() -> None:
    """A non-owner cannot add users."""
    update = _make_update(user_id=99)
    context = _make_context(args=["123"], owner_id=1)
    await cmd_adduser(update, context)
    text = update.message.reply_text.call_args.args[0]
    assert "owner" in text.lower()


@pytest.mark.asyncio
async def test_cmd_adduser_success() -> None:
    update = _make_update(user_id=1)
    user_repo = MagicMock(add_user=AsyncMock(return_value=True))
    context = _make_context(args=["456"], owner_id=1, user_repo=user_repo)
    await cmd_adduser(update, context)
    user_repo.add_user.assert_called_once_with(user_id=456, added_by=1)
    text = update.message.reply_text.call_args.args[0]
    assert "456" in text


@pytest.mark.asyncio
async def test_cmd_removeuser_owner_only() -> None:
    update = _make_update(user_id=99)
    context = _make_context(args=["123"], owner_id=1)
    await cmd_removeuser(update, context)
    text = update.message.reply_text.call_args.args[0]
    assert "owner" in text.lower()


@pytest.mark.asyncio
async def test_cmd_users_lists_ids() -> None:
    update = _make_update(user_id=1)
    user_repo = MagicMock(get_allowed_user_ids=AsyncMock(return_value=[10, 20]))
    context = _make_context(owner_id=1, user_repo=user_repo)
    await cmd_users(update, context)
    text = update.message.reply_text.call_args.args[0]
    assert "10" in text
    assert "20" in text
