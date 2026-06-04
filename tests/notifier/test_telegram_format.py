"""The rendered notification text must be clean: no duplicate tracking number,
carrier shown, human dates, localized status."""

from __future__ import annotations

from typing import Any

import pytest

from parcel_tracker.db.models import ShipmentStatus, TrackingEvent
from parcel_tracker.notifier.telegram import TelegramNotifier


class _CaptureBot:
    def __init__(self) -> None:
        self.messages: list[dict[str, Any]] = []
        self.photos: list[dict[str, Any]] = []

    async def send_message(
        self,
        *,
        chat_id: int,
        text: str,
        parse_mode: str = "HTML",
        reply_markup: object = None,
    ) -> object:
        self.messages.append({"chat_id": chat_id, "text": text})
        return object()

    async def send_photo(
        self,
        *,
        chat_id: int,
        photo: object,
        caption: str,
        parse_mode: str = "HTML",
    ) -> object:
        self.photos.append({"chat_id": chat_id, "caption": caption})
        return object()


@pytest.mark.asyncio
async def test_events_update_no_duplicate_number_and_has_carrier() -> None:
    bot = _CaptureBot()
    notifier = TelegramNotifier(bot=bot)
    await notifier.send_events_update(
        chat_id=1,
        tracking_number="1Z999AA10123456784",
        parcel_name=None,
        carrier_name="UPS",
        old_status=ShipmentStatus.INFO_RECEIVED,
        new_status=ShipmentStatus.IN_TRANSIT,
        status_changed=True,
        new_events=[
            TrackingEvent(
                time="2026-06-04T03:45:00+02:00",
                description="Departed from Facility",
                location="Milano, IT",
            )
        ],
        location="Milano, IT",
        map_png=None,
    )
    text = bot.messages[0]["text"]
    # tracking number appears exactly once
    assert text.count("1Z999AA10123456784") == 1
    # carrier present in the header
    assert "UPS" in text
    # human date, not raw ISO
    assert "04/06/2026 03:45" in text
    assert "2026-06-04T03:45:00+02:00" not in text
    # localized-baseline status label, not raw enum value
    assert "In transit" in text
    assert "InTransit" not in text


@pytest.mark.asyncio
async def test_events_update_uses_parcel_name_when_set() -> None:
    bot = _CaptureBot()
    notifier = TelegramNotifier(bot=bot)
    await notifier.send_events_update(
        chat_id=1,
        tracking_number="ABC123456",
        parcel_name="Amazon order",
        carrier_name="UPS",
        old_status=ShipmentStatus.IN_TRANSIT,
        new_status=ShipmentStatus.IN_TRANSIT,
        status_changed=False,
        new_events=[TrackingEvent(time="2026-06-04T05:24:00Z", description="Processing")],
        location=None,
        map_png=None,
    )
    text = bot.messages[0]["text"]
    assert "Amazon order" in text
    assert text.count("ABC123456") == 1
