from unittest.mock import AsyncMock, MagicMock

import pytest

from parcel_tracker.bot.parcel_commands import cmd_status
from parcel_tracker.db.models import Parcel, ShipmentStatus


@pytest.mark.asyncio
async def test_cmd_status_shows_position() -> None:
    repo = MagicMock()
    repo.get_by_tracking_number = AsyncMock(
        return_value=Parcel(tracking_number="TN1", user_id=7, status=ShipmentStatus.IN_TRANSIT,
                            last_event="Departed facility", last_location="Milano, Italy")
    )
    update = MagicMock()
    update.effective_message = MagicMock()
    update.effective_message.reply_text = AsyncMock()
    context = MagicMock()
    context.args = ["TN1"]
    context.bot_data = {"parcel_repo": repo}
    await cmd_status(update, context)
    out = update.effective_message.reply_text.await_args.args[0]
    assert "Milano, Italy" in out
    assert "Departed facility" in out
