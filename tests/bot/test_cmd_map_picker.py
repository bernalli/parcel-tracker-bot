from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from parcel_tracker.bot import navigation_commands
from parcel_tracker.db.models import Parcel


@pytest.mark.asyncio
async def test_map_without_args_shows_picker() -> None:
    repo = AsyncMock()
    repo.list_active_for_user.return_value = [Parcel(tracking_number="A", user_id=10)]
    reply = AsyncMock()
    update = SimpleNamespace(
        effective_user=SimpleNamespace(id=10),
        effective_message=SimpleNamespace(reply_text=reply, chat_id=1),
    )
    context = SimpleNamespace(args=[], bot_data={"parcel_repo": repo})
    await navigation_commands.cmd_map(update, context)
    # a picker keyboard was sent, NOT the "usage" text
    assert reply.await_args is not None
    kwargs = reply.await_args.kwargs
    assert "reply_markup" in kwargs and kwargs["reply_markup"] is not None
