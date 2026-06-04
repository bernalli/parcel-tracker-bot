from unittest.mock import AsyncMock, MagicMock

import pytest

from parcel_tracker.db.models import ShipmentStatus, TrackingEvent
from parcel_tracker.notifier.telegram import TelegramNotifier


@pytest.mark.asyncio
async def test_send_events_update_includes_new_events_and_location() -> None:
    bot = MagicMock()
    bot.send_message = AsyncMock()
    n = TelegramNotifier(bot=bot)
    await n.send_events_update(
        chat_id=7, tracking_number="TN1", parcel_name="amz",
        old_status=ShipmentStatus.IN_TRANSIT, new_status=ShipmentStatus.IN_TRANSIT,
        status_changed=False, location="Milano, Italy",
        new_events=[TrackingEvent(time="2026-06-04T10:00:00Z", description="Departed",
                                  location="Milano, Italy")],
    )
    text = bot.send_message.await_args.kwargs["text"]
    assert "Departed" in text
    assert "Milano, Italy" in text
