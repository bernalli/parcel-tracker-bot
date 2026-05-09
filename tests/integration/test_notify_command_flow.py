"""End-to-end smoke for /notify flow with a real DB."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from parcel_tracker.bot.notify_commands import cmd_notify_dispatch
from parcel_tracker.db.migrations import init_schema
from parcel_tracker.db.notification_repository import NotificationRepository


@pytest.mark.asyncio
async def test_notify_on_persists_to_db(tmp_path: Path) -> None:
    db = str(tmp_path / "n.db")
    await init_schema(db)
    repo = NotificationRepository(db)

    update = MagicMock()
    update.effective_user.id = 42
    update.message.reply_text = AsyncMock()
    context = MagicMock()
    context.args = ["on", "InTransit"]
    context.bot_data = {"notification_repo": repo}

    await cmd_notify_dispatch(update, context)
    assert await repo.get_pref(42, "InTransit") is True


@pytest.mark.asyncio
async def test_notify_all_then_none_round_trip(tmp_path: Path) -> None:
    db = str(tmp_path / "n.db")
    await init_schema(db)
    repo = NotificationRepository(db)

    update = MagicMock()
    update.effective_user.id = 1
    update.message.reply_text = AsyncMock()
    context_all = MagicMock()
    context_all.args = ["all"]
    context_all.bot_data = {"notification_repo": repo}

    await cmd_notify_dispatch(update, context_all)
    prefs = await repo.get_all_prefs(1)
    assert all(prefs.values())

    context_none = MagicMock()
    context_none.args = ["none"]
    context_none.bot_data = {"notification_repo": repo}

    await cmd_notify_dispatch(update, context_none)
    prefs = await repo.get_all_prefs(1)
    assert not any(prefs.values())
