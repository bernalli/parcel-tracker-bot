"""A failed terminal notification is retried on later ticks instead of being lost (#17)."""

from __future__ import annotations

import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from parcel_tracker.core.scheduler import check_updates
from parcel_tracker.core.tracker_base import AbstractTracker, TrackingResult
from parcel_tracker.db.models import Parcel, ShipmentStatus, TrackingEvent


class _T(AbstractTracker):
    name = "fake"
    priority = 10
    tracking_id_patterns = [re.compile(r"^FAKE\d+$")]

    def __init__(self, r: TrackingResult) -> None:
        self._r = r

    async def fetch(self, tracking_id: str) -> TrackingResult:
        return self._r


async def _bot_data(tmp_path: Path, result: TrackingResult) -> dict[str, Any]:
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
        metrics_port=19091,
        batch_size=5,
        rate_limit_default_per_min=600,
        rate_limit_overrides={},
        admin_user_ids=frozenset({7}),
    )
    bot_data = await build_bot_data(cfg)
    detector = MagicMock()
    detector.detect.return_value = [_T(result)]
    bot_data["detector"] = detector
    bot_data["prefs"] = None
    bot_data["notifier"] = MagicMock()
    bot_data["notifier"].send_delivery_confirmation = AsyncMock()
    bot_data["notifier"].send_events_update = AsyncMock()
    bot_data["now"] = lambda: datetime(2026, 6, 4, 12, 0, tzinfo=UTC)
    await bot_data["parcel_repo"].create(
        Parcel(tracking_number="FAKE1", user_id=7, status=ShipmentStatus.OUT_FOR_DELIVERY)
    )
    return bot_data


def _result(status: ShipmentStatus) -> TrackingResult:
    ev = TrackingEvent(time="2026-06-04T10:00:00Z", description=status.value, location="Milano")
    return TrackingResult(
        tracking_number="FAKE1",
        found=True,
        status=status,
        last_event=status.value,
        last_event_time=ev.time,
        last_location="Milano",
        events=[ev],
    )


@pytest.mark.asyncio
async def test_failed_delivery_prompt_is_retried_next_tick(tmp_path: Path) -> None:
    bot_data = await _bot_data(tmp_path, _result(ShipmentStatus.DELIVERED))
    send = bot_data["notifier"].send_delivery_confirmation
    send.side_effect = [TimeoutError("telegram"), None]
    ctx = MagicMock()
    ctx.bot_data = bot_data

    await check_updates(ctx)
    repo = bot_data["parcel_repo"]
    parcel = await repo.get_for_user("FAKE1", user_id=7)
    assert parcel is not None
    assert parcel.status is ShipmentStatus.DELIVERED
    assert parcel.delivered_at is None  # not stamped while the prompt is undelivered

    await check_updates(ctx)
    assert send.await_count == 2
    parcel = await repo.get_for_user("FAKE1", user_id=7)
    assert parcel is not None
    assert parcel.delivered_at is not None
    assert await repo.get_unnotified("FAKE1", user_id=7) == []

    await check_updates(ctx)
    assert send.await_count == 2  # delivered once, never re-prompted


@pytest.mark.asyncio
async def test_failed_expired_update_is_retried_next_tick(tmp_path: Path) -> None:
    bot_data = await _bot_data(tmp_path, _result(ShipmentStatus.EXPIRED))
    outcomes: list[Exception | None] = [TimeoutError("telegram"), None]

    async def _send_events_update(**kwargs: Any) -> None:
        # Behave like TelegramNotifier: report delivered events through the callback.
        outcome = outcomes.pop(0) if outcomes else None
        if outcome is not None:
            raise outcome
        if kwargs.get("on_events_sent") is not None:
            await kwargs["on_events_sent"](kwargs["new_events"])

    send = bot_data["notifier"].send_events_update
    send.side_effect = _send_events_update
    ctx = MagicMock()
    ctx.bot_data = bot_data
    repo = bot_data["parcel_repo"]

    await check_updates(ctx)
    assert len(await repo.get_unnotified("FAKE1", user_id=7)) == 1

    await check_updates(ctx)
    assert send.await_count == 2
    assert await repo.get_unnotified("FAKE1", user_id=7) == []

    await check_updates(ctx)
    assert send.await_count == 2


@pytest.mark.asyncio
async def test_manual_refresh_after_failed_prompt_stamps_delivery(tmp_path: Path) -> None:
    from parcel_tracker.core.scheduler import check_parcel_now

    bot_data = await _bot_data(tmp_path, _result(ShipmentStatus.DELIVERED))
    send = bot_data["notifier"].send_delivery_confirmation
    send.side_effect = [TimeoutError("telegram"), None]
    ctx = MagicMock()
    ctx.bot_data = bot_data

    await check_updates(ctx)
    await check_parcel_now(bot_data, user_id=7, tracking_number="FAKE1")
    assert send.await_count == 2

    await check_updates(ctx)
    assert send.await_count == 2  # the sweep does not prompt a second time
