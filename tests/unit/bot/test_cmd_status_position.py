from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from parcel_tracker.bot import parcel_commands
from parcel_tracker.bot.parcel_commands import cmd_status
from parcel_tracker.db.models import Parcel, ShipmentStatus


@pytest.mark.asyncio
async def test_cmd_status_shows_position() -> None:
    repo = MagicMock()
    repo.get_for_user = AsyncMock(
        return_value=Parcel(
            tracking_number="TN1",
            user_id=7,
            status=ShipmentStatus.IN_TRANSIT,
            last_event="Departed facility",
            last_location="Milano, Italy",
        )
    )
    update = MagicMock()
    update.effective_user = MagicMock(id=7)
    update.effective_message = MagicMock()
    update.effective_message.reply_text = AsyncMock()
    context = MagicMock()
    context.args = ["TN1"]
    context.bot_data = {"parcel_repo": repo}
    await cmd_status(update, context)
    out = update.effective_message.reply_text.await_args.args[0]
    assert "Milano, Italy" in out
    assert "Departed facility" in out


@pytest.mark.asyncio
async def test_status_replies_with_card_and_actions_keyboard() -> None:
    repo = AsyncMock()
    repo.get_for_user.return_value = Parcel(
        tracking_number="TN1", user_id=10, name="iPhone", status=ShipmentStatus.IN_TRANSIT
    )
    reply = AsyncMock()
    update = SimpleNamespace(
        effective_user=SimpleNamespace(id=10),
        effective_message=SimpleNamespace(reply_text=reply),
    )
    context = SimpleNamespace(args=["TN1"], bot_data={"parcel_repo": repo})
    await parcel_commands.cmd_status(update, context)  # type: ignore[arg-type]
    text = reply.await_args.args[0]
    assert "📦 <b>iPhone</b>" in text
    assert "🚚" in text  # status emoji, non enum raw
    assert "InTransit" not in text  # mai il valore enum grezzo
    markup = reply.await_args.kwargs["reply_markup"]
    flat = [b.callback_data for row in markup.inline_keyboard for b in row]
    assert "parcel:refresh:TN1" in flat
