"""A poll and a manual refresh of the same parcel never notify twice (#18)."""

from __future__ import annotations

import asyncio
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from parcel_tracker.core import scheduler
from parcel_tracker.core.scheduler import check_parcel_now, check_updates, check_user_now
from parcel_tracker.core.tracker_base import AbstractTracker, TrackingResult
from parcel_tracker.db.models import Parcel, ShipmentStatus, TrackingEvent


class _SlowTracker(AbstractTracker):
    """Returns DELIVERED, but only once ``release`` is set, so calls overlap."""

    name = "fake"
    priority = 10
    tracking_id_patterns = [re.compile(r"^FAKE\d+$")]

    def __init__(self) -> None:
        self.release = asyncio.Event()
        self.calls = 0

    async def fetch(self, tracking_id: str) -> TrackingResult:
        self.calls += 1
        await self.release.wait()
        ev = TrackingEvent(time="2026-06-04T10:00:00Z", description="Delivered", location="Milano")
        return TrackingResult(
            tracking_number=tracking_id,
            found=True,
            status=ShipmentStatus.DELIVERED,
            last_event="Delivered",
            last_event_time=ev.time,
            last_location="Milano",
            events=[ev],
        )


async def _bot_data(tmp_path: Path, tracker: AbstractTracker) -> dict[str, Any]:
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
        metrics_port=19093,
        batch_size=5,
        rate_limit_default_per_min=600,
        rate_limit_overrides={},
        admin_user_ids=frozenset({7}),
    )
    bot_data = await build_bot_data(cfg)
    detector = MagicMock()
    detector.detect.return_value = [tracker]
    notifier = MagicMock()
    notifier.send_delivery_confirmation = AsyncMock()
    notifier.send_events_update = AsyncMock()
    bot_data.update(
        detector=detector,
        prefs=None,
        notifier=notifier,
        now=lambda: datetime(2026, 6, 4, 12, 0, tzinfo=UTC),
    )
    await bot_data["parcel_repo"].create(
        Parcel(tracking_number="FAKE1", user_id=7, status=ShipmentStatus.OUT_FOR_DELIVERY)
    )
    return bot_data


async def _until(predicate: Any) -> None:
    for _ in range(200):
        if predicate():
            return
        await asyncio.sleep(0.01)
    raise AssertionError("condition not reached")


@pytest.mark.asyncio
async def test_poll_and_manual_refresh_prompt_once(tmp_path: Path) -> None:
    tracker = _SlowTracker()
    bot_data = await _bot_data(tmp_path, tracker)
    ctx = MagicMock()
    ctx.bot_data = bot_data

    poll = asyncio.create_task(check_updates(ctx))
    await _until(lambda: tracker.calls == 1)
    refresh = asyncio.create_task(check_parcel_now(bot_data, user_id=7, tracking_number="FAKE1"))
    await asyncio.sleep(0.05)
    tracker.release.set()
    await asyncio.gather(poll, refresh)

    bot_data["notifier"].send_delivery_confirmation.assert_awaited_once()
    assert scheduler._CHECK_LOCKS == {}


@pytest.mark.asyncio
async def test_checkall_during_poll_prompts_once(tmp_path: Path) -> None:
    tracker = _SlowTracker()
    bot_data = await _bot_data(tmp_path, tracker)
    ctx = MagicMock()
    ctx.bot_data = bot_data

    poll = asyncio.create_task(check_updates(ctx))
    await _until(lambda: tracker.calls == 1)
    checkall = asyncio.create_task(check_user_now(bot_data, user_id=7))
    await asyncio.sleep(0.05)
    tracker.release.set()
    await asyncio.gather(poll, checkall)

    bot_data["notifier"].send_delivery_confirmation.assert_awaited_once()


@pytest.mark.asyncio
async def test_different_users_do_not_wait_for_each_other() -> None:
    async with scheduler._parcel_check_lock(1, "X") as waited_a:
        async with scheduler._parcel_check_lock(2, "X") as waited_b:
            assert (waited_a, waited_b) == (False, False)
    assert scheduler._CHECK_LOCKS == {}
