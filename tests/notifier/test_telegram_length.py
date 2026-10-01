"""Long event backlogs are split under Telegram's limits and marked per batch (#21)."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from parcel_tracker.db.models import ShipmentStatus, TrackingEvent
from parcel_tracker.notifier.telegram import (
    MAX_CAPTION_CHARS,
    MAX_MESSAGE_CHARS,
    TelegramNotifier,
    _visible_len,
)


def _events(n: int, desc_len: int = 120) -> list[TrackingEvent]:
    return [
        TrackingEvent(
            time=f"2026-06-{1 + i % 28:02d}T10:00:00Z",
            description=f"{i:04d} " + "x" * desc_len,
            location="Milano & Lodi",
        )
        for i in range(n)
    ]


async def _send(
    notifier: TelegramNotifier,
    events: list[TrackingEvent],
    *,
    map_png: bytes | None = None,
    on_events_sent: AsyncMock | None = None,
) -> None:
    await notifier.send_events_update(
        chat_id=1,
        tracking_number="TN1",
        parcel_name=None,
        old_status=ShipmentStatus.IN_TRANSIT,
        new_status=ShipmentStatus.IN_TRANSIT,
        status_changed=False,
        new_events=events,
        location="Milano",
        map_png=map_png,
        on_events_sent=on_events_sent,
    )


@pytest.mark.asyncio
async def test_long_backlog_is_split_into_bounded_messages() -> None:
    bot = SimpleNamespace(send_message=AsyncMock(), send_photo=AsyncMock())
    events = _events(200)
    await _send(TelegramNotifier(bot=bot), events)

    texts = [c.kwargs["text"] for c in bot.send_message.await_args_list]
    assert len(texts) > 1
    assert all(_visible_len(t) <= MAX_MESSAGE_CHARS for t in texts)
    # Every event appears exactly once across the messages.
    for ev in events:
        assert sum(ev.description[:5] in t for t in texts) == 1


@pytest.mark.asyncio
async def test_oversized_single_event_is_clipped() -> None:
    bot = SimpleNamespace(send_message=AsyncMock(), send_photo=AsyncMock())
    await _send(TelegramNotifier(bot=bot), _events(1, desc_len=20_000))
    text = bot.send_message.await_args.kwargs["text"]
    assert _visible_len(text) <= MAX_MESSAGE_CHARS


@pytest.mark.asyncio
async def test_long_backlog_with_map_keeps_caption_short() -> None:
    bot = SimpleNamespace(send_message=AsyncMock(), send_photo=AsyncMock())
    await _send(TelegramNotifier(bot=bot), _events(50), map_png=b"png")
    caption = bot.send_photo.await_args.kwargs["caption"]
    assert _visible_len(caption) <= MAX_CAPTION_CHARS
    assert bot.send_message.await_count >= 1


@pytest.mark.asyncio
async def test_partial_failure_reports_only_delivered_batches() -> None:
    bot = SimpleNamespace(
        send_message=AsyncMock(side_effect=[None, TimeoutError("telegram")]),
        send_photo=AsyncMock(),
    )
    events = _events(200)
    sent = AsyncMock()
    with pytest.raises(TimeoutError):
        await _send(TelegramNotifier(bot=bot), events, on_events_sent=sent)

    sent.assert_awaited_once()
    first_batch = sent.await_args.args[0]
    assert 0 < len(first_batch) < len(events)
    assert first_batch == events[: len(first_batch)]
