# tests/bot/test_cmd_checkall.py
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from parcel_tracker.bot import parcel_commands


@pytest.mark.asyncio
async def test_cmd_checkall_runs_and_reports(monkeypatch) -> None:
    reply = AsyncMock()
    update = SimpleNamespace(
        effective_user=SimpleNamespace(id=10),
        effective_message=SimpleNamespace(reply_text=reply),
        message=SimpleNamespace(reply_text=reply),
    )
    context = SimpleNamespace(args=[], bot_data={"x": 1})

    async def fake_check_user_now(bot_data, *, user_id):
        return 3

    monkeypatch.setattr(parcel_commands, "check_user_now", fake_check_user_now, raising=False)
    await parcel_commands.cmd_checkall(update, context)
    assert reply.await_count >= 1
