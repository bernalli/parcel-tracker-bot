"""Tests for notifier.telegram."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

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


@pytest.mark.asyncio
async def test_send_status_update_increments_sent_counter() -> None:
    from parcel_tracker.observability.metrics import TELEGRAM_SENT_TOTAL

    bot = MagicMock()
    bot.send_message = AsyncMock()
    notifier = TelegramNotifier(bot=bot)

    before = TELEGRAM_SENT_TOTAL.labels(status_value="Delivered")._value.get()
    await notifier.send_status_update(
        chat_id=1,
        tracking_number="ABC",
        parcel_name="Test",
        old_status=ShipmentStatus.IN_TRANSIT,
        new_status=ShipmentStatus.DELIVERED,
        last_event=None,
    )
    after = TELEGRAM_SENT_TOTAL.labels(status_value="Delivered")._value.get()
    assert after == before + 1.0


@pytest.mark.asyncio
async def test_send_status_update_increments_errors_on_telegram_error() -> None:
    from parcel_tracker.observability.metrics import TELEGRAM_ERRORS_TOTAL

    class _Boom(Exception):
        pass

    bot = MagicMock()
    bot.send_message = AsyncMock(side_effect=_Boom("test"))
    notifier = TelegramNotifier(bot=bot)

    before = TELEGRAM_ERRORS_TOTAL.labels(error_class="_Boom")._value.get()
    with pytest.raises(_Boom):
        await notifier.send_status_update(
            chat_id=1,
            tracking_number="ABC",
            parcel_name="Test",
            old_status=ShipmentStatus.IN_TRANSIT,
            new_status=ShipmentStatus.DELIVERED,
            last_event=None,
        )
    after = TELEGRAM_ERRORS_TOTAL.labels(error_class="_Boom")._value.get()
    assert after == before + 1.0
