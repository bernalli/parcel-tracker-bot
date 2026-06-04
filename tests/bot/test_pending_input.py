from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from parcel_tracker.bot import parcel_commands


@pytest.mark.asyncio
async def test_pending_rename_consumes_next_message() -> None:
    repo = AsyncMock()
    repo.rename.return_value = True
    reply = AsyncMock()
    update = SimpleNamespace(
        effective_user=SimpleNamespace(id=10),
        message=SimpleNamespace(text="My new name", reply_text=reply),
    )
    context = SimpleNamespace(
        args=[],
        bot_data={"parcel_repo": repo},
        user_data={"pending": {"action": "rename", "tn": "TN1"}},
    )
    await parcel_commands.handle_message(update, context)  # type: ignore[arg-type]
    repo.rename.assert_awaited_once_with("TN1", user_id=10, name="My new name")
    assert "pending" not in context.user_data  # state cleared


@pytest.mark.asyncio
async def test_no_pending_falls_through_to_autoadd() -> None:
    repo = AsyncMock()
    repo.create.return_value = object()
    reply = AsyncMock()
    update = SimpleNamespace(
        effective_user=SimpleNamespace(id=10),
        message=SimpleNamespace(text="1Z999AA10123456784", reply_text=reply),
    )
    context = SimpleNamespace(
        args=[], bot_data={"parcel_repo": repo, "detector": None}, user_data={}
    )
    await parcel_commands.handle_message(update, context)  # type: ignore[arg-type]
    repo.create.assert_awaited()  # auto-add path still works
