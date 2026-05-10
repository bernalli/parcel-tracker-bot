"""End-to-end smoke for /health command flow with a real HealthRepository."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from parcel_tracker.bot.health_commands import cmd_health
from parcel_tracker.db.health_repository import HealthRepository
from parcel_tracker.db.migrations import init_schema


@pytest.mark.asyncio
async def test_cmd_health_with_real_repository(tmp_path) -> None:
    db_path = str(tmp_path / "health.db")
    await init_schema(db_path)
    repo = HealthRepository(db_path)
    await repo.record_success("dhl", "")
    await repo.record_failure("dhl", "")  # 1 failure / 2 checks → 50% success

    fake_dhl = MagicMock()
    fake_dhl.name = "dhl"
    registry = MagicMock()
    registry.iter_all = MagicMock(return_value=iter([fake_dhl]))

    update = MagicMock()
    update.message.reply_text = AsyncMock()
    update.effective_message = update.message
    context = MagicMock()
    context.bot_data = {
        "registry": registry,
        "health_repo": repo,
        "config": MagicMock(admin_user_ids=frozenset()),
    }

    await cmd_health(update, context)
    text = update.message.reply_text.call_args.args[0]
    assert "dhl" in text
    # 50% < 80% threshold → red
    assert "🔴" in text
