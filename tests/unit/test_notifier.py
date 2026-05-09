"""Tests for notifier.telegram."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from parcel_tracker.db.models import ShipmentStatus, TrackingEvent
from parcel_tracker.notifier.telegram import TelegramNotifier


@pytest.mark.asyncio
async def test_send_status_update_calls_bot() -> None:
    bot = AsyncMock()
    notifier = TelegramNotifier(bot=bot)

    await notifier.send_status_update(
        chat_id=42,
        tracking_number="ABC123",
        parcel_name="Pacchetto",
        old_status=ShipmentStatus.IN_TRANSIT,
        new_status=ShipmentStatus.DELIVERED,
        last_event=TrackingEvent(time="now", description="Delivered", location="Milano"),
    )

    bot.send_message.assert_called_once()
    args = bot.send_message.call_args
    assert args.kwargs["chat_id"] == 42
    assert "Delivered" in args.kwargs["text"] or "DELIVERED" in args.kwargs["text"].upper()
