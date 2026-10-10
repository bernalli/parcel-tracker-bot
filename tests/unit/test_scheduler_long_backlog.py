"""A long backlog is delivered in batches; a failure keeps only undelivered events (#21)."""

from __future__ import annotations

import re
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from parcel_tracker.core.scheduler import check_updates
from parcel_tracker.core.tracker_base import AbstractTracker, TrackingResult
from parcel_tracker.db.models import Parcel, ShipmentStatus, TrackingEvent
from parcel_tracker.notifier.telegram import MAX_MESSAGE_CHARS, TelegramNotifier, _visible_len


class _T(AbstractTracker):
    name = "fake"
    priority = 10
    tracking_id_patterns = [re.compile(r"^FAKE\d+$")]

    def __init__(self, r: TrackingResult) -> None:
        self._r = r

    async def fetch(self, tracking_id: str) -> TrackingResult:
        return self._r


@pytest.mark.asyncio
async def test_long_backlog_survives_a_failed_batch(tmp_path: Path) -> None:
    from parcel_tracker.config import Config
    from parcel_tracker.main import build_bot_data

    cfg = Config(
        telegram_bot_token="fake",  # noqa: S106
        owner_id=7,
        allowed_user_ids=[7],
        database_path=str(tmp_path / "t.db"),
        log_level="INFO",
        log_format="json",
        metrics_enabled=False,
        metrics_bind_host="127.0.0.1",
        metrics_port=19092,
        batch_size=5,
        rate_limit_default_per_min=600,
        rate_limit_overrides={},
        admin_user_ids=frozenset({7}),
    )
    bot_data = await build_bot_data(cfg)
    events = [
        TrackingEvent(
            time=f"2026-05-{1 + i % 28:02d}T{i % 24:02d}:{i % 60:02d}:00Z",
            description=f"Event {i:04d} " + "y" * 150,
            location="Hub",
        )
        for i in range(150)
    ]
    result = TrackingResult(
        tracking_number="FAKE1",
        found=True,
        status=ShipmentStatus.IN_TRANSIT,
        last_event=events[0].description,
        last_event_time=events[0].time,
        last_location="Hub",
        events=events,
    )
    detector = MagicMock()
    detector.detect.return_value = [_T(result)]
    bot = SimpleNamespace(
        send_message=AsyncMock(side_effect=[None, TimeoutError("telegram")]),
        send_photo=AsyncMock(),
    )
    bot_data.update(
        detector=detector,
        prefs=None,
        notifier=TelegramNotifier(bot=bot),
        now=lambda: datetime(2026, 6, 4, 12, 0, tzinfo=UTC),
    )
    repo = bot_data["parcel_repo"]
    await repo.create(Parcel(tracking_number="FAKE1", user_id=7, status=ShipmentStatus.PICKUP))
    ctx = MagicMock()
    ctx.bot_data = bot_data

    await check_updates(ctx)

    texts = [c.kwargs["text"] for c in bot.send_message.await_args_list]
    assert all(_visible_len(t) <= MAX_MESSAGE_CHARS for t in texts)
    pending = await repo.get_unnotified("FAKE1", user_id=7)
    # The first message went out and its events are no longer pending; the rest are.
    assert 0 < len(pending) < len(events)
