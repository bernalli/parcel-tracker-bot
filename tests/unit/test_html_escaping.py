"""Tests for HTML escaping of untrusted values in bot output."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from parcel_tracker.db.models import ShipmentStatus, TrackingEvent
from parcel_tracker.notifier.telegram import TelegramNotifier


@pytest.mark.asyncio
async def test_events_update_escapes_html_in_event_fields() -> None:
    bot = MagicMock()
    bot.send_message = AsyncMock()
    n = TelegramNotifier(bot=bot)
    await n.send_events_update(
        chat_id=7, tracking_number="TN<1>", parcel_name="a & b",
        old_status=ShipmentStatus.IN_TRANSIT, new_status=ShipmentStatus.IN_TRANSIT,
        status_changed=False, location="C<ity>",
        new_events=[TrackingEvent(time="t", description="<b>boom</b>", location="x & y")],
    )
    text = bot.send_message.await_args.kwargs["text"]
    assert "<b>boom</b>" not in text         # the untrusted value must be escaped
    assert "&lt;b&gt;boom&lt;/b&gt;" in text  # escaped form present
    assert "a &amp; b" in text                # parcel name escaped
    # Our own formatting tags remain literal:
    assert "<code>" in text


@pytest.mark.asyncio
async def test_status_update_escapes_html() -> None:
    bot = MagicMock()
    bot.send_message = AsyncMock()
    n = TelegramNotifier(bot=bot)
    await n.send_status_update(
        chat_id=7, tracking_number="X", parcel_name="<i>n</i>",
        old_status=ShipmentStatus.IN_TRANSIT, new_status=ShipmentStatus.DELIVERED,
        last_event=TrackingEvent(time="t", description="<script>", location=None),
    )
    text = bot.send_message.await_args.kwargs["text"]
    assert "<script>" not in text
    assert "&lt;script&gt;" in text
