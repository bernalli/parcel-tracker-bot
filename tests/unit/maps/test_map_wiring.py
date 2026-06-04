from unittest.mock import AsyncMock, MagicMock

import pytest

from parcel_tracker.db.models import ShipmentStatus, TrackingEvent
from parcel_tracker.notifier.telegram import TelegramNotifier


@pytest.mark.asyncio
async def test_send_events_update_sends_photo_when_map_present() -> None:
    bot = MagicMock()
    bot.send_message = AsyncMock()
    bot.send_photo = AsyncMock()
    n = TelegramNotifier(bot=bot)
    await n.send_events_update(
        chat_id=7, tracking_number="TN1", parcel_name="amz",
        old_status=ShipmentStatus.IN_TRANSIT, new_status=ShipmentStatus.IN_TRANSIT,
        status_changed=False, location="Milano, Italy",
        new_events=[TrackingEvent(time="t", description="Departed", location="Milano, Italy")],
        map_png=b"\x89PNG\r\n\x1a\n....",
    )
    bot.send_photo.assert_awaited_once()
    bot.send_message.assert_not_awaited()


@pytest.mark.asyncio
async def test_send_events_update_text_when_no_map() -> None:
    bot = MagicMock()
    bot.send_message = AsyncMock()
    bot.send_photo = AsyncMock()
    n = TelegramNotifier(bot=bot)
    await n.send_events_update(
        chat_id=7, tracking_number="TN1", parcel_name="amz",
        old_status=ShipmentStatus.IN_TRANSIT, new_status=ShipmentStatus.IN_TRANSIT,
        status_changed=False, location=None, new_events=[],
    )
    bot.send_message.assert_awaited_once()
    bot.send_photo.assert_not_awaited()
