import re
from unittest.mock import AsyncMock, MagicMock

import pytest

from parcel_tracker.bot.parcel_commands import handle_message
from parcel_tracker.core.tracker_base import AbstractTracker


class _Ups(AbstractTracker):
    name = "ups"
    priority = 90
    tracking_id_patterns = [re.compile(r"^1Z[0-9A-Z]{16}$")]

    async def fetch(self, tracking_id: str):  # pragma: no cover
        raise NotImplementedError


def _update(text: str) -> MagicMock:
    update = MagicMock()
    update.message = MagicMock()
    update.message.text = text
    update.message.reply_text = AsyncMock()
    update.effective_user = MagicMock(id=7)
    return update


def _context(created) -> MagicMock:
    repo = MagicMock()
    repo.create = AsyncMock(return_value=created)
    detector = MagicMock()
    detector.detect.return_value = [_Ups()]
    context = MagicMock()
    context.bot_data = {"parcel_repo": repo, "detector": detector}
    return context


@pytest.mark.asyncio
async def test_auto_add_creates_on_valid_code() -> None:
    from parcel_tracker.db.models import Parcel

    update = _update("1Z999AA10123456784")
    ctx = _context(created=Parcel(tracking_number="1Z999AA10123456784", user_id=7))
    await handle_message(update, ctx)
    ctx.bot_data["parcel_repo"].create.assert_awaited_once()


@pytest.mark.asyncio
async def test_auto_add_ignores_chat_text() -> None:
    update = _update("ciao come stai")
    ctx = _context(created=None)
    track17 = MagicMock()
    track17.priority = 1
    ctx.bot_data["detector"].detect.return_value = [track17]  # only universal matcher
    await handle_message(update, ctx)
    ctx.bot_data["parcel_repo"].create.assert_not_awaited()
