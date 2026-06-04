"""Test for cmd_rename implementation."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from parcel_tracker.bot import parcel_commands


@pytest.mark.asyncio
async def test_cmd_rename_calls_repo_and_confirms() -> None:
    repo = AsyncMock()
    repo.rename.return_value = True
    reply = AsyncMock()
    update = SimpleNamespace(
        effective_user=SimpleNamespace(id=10),
        effective_message=SimpleNamespace(reply_text=reply),
        message=SimpleNamespace(reply_text=reply),
    )
    context = SimpleNamespace(args=["TN1", "new", "name"], bot_data={"parcel_repo": repo})
    await parcel_commands.cmd_rename(update, context)
    repo.rename.assert_awaited_once_with("TN1", user_id=10, name="new name")
    reply.assert_awaited()


@pytest.mark.asyncio
async def test_cmd_rename_not_found() -> None:
    repo = AsyncMock()
    repo.rename.return_value = False
    reply = AsyncMock()
    update = SimpleNamespace(
        effective_user=SimpleNamespace(id=10),
        effective_message=SimpleNamespace(reply_text=reply),
        message=SimpleNamespace(reply_text=reply),
    )
    context = SimpleNamespace(args=["TNX", "whatever"], bot_data={"parcel_repo": repo})
    await parcel_commands.cmd_rename(update, context)
    repo.rename.assert_awaited_once()
    from parcel_tracker.bot import messages

    reply.assert_awaited_once_with(messages.parcel_not_found("TNX"), parse_mode="HTML")
