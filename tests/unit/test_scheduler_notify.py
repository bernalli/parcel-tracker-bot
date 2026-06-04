from __future__ import annotations

import re
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from parcel_tracker.core.rate_limiter import RateLimiter
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


def _ctx(parcel: Parcel, result: TrackingResult, new_events: list[TrackingEvent]) -> MagicMock:
    detector = MagicMock()
    detector.detect.return_value = [_T(result)]
    repo = MagicMock()
    repo.list_active_for_user = AsyncMock(return_value=[parcel])
    repo.set_last_check_at = AsyncMock()
    repo.update_status = AsyncMock()
    repo.add_events_dedup = AsyncMock(return_value=new_events)
    repo.update_latest = AsyncMock()
    repo.set_delivered = AsyncMock()
    repo.get_history = AsyncMock(return_value=[])
    user_repo = MagicMock()
    user_repo.get_allowed_user_ids = AsyncMock(return_value=[])
    health = MagicMock()
    health.is_quarantined = AsyncMock(return_value=False)
    health.record_success = AsyncMock()
    health.record_failure = AsyncMock()
    notifier = MagicMock()
    notifier.send_events_update = AsyncMock()
    notifier.send_delivery_confirmation = AsyncMock()
    config = MagicMock()
    config.batch_size = 10
    config.owner_id = 7
    config.allowed_user_ids = []
    prefs = MagicMock()
    prefs.is_status_enabled = AsyncMock(return_value=True)
    ctx = MagicMock()
    ctx.bot_data = {
        "parcel_repo": repo,
        "registry": MagicMock(),
        "detector": detector,
        "health": health,
        "notifier": notifier,
        "user_repo": user_repo,
        "config": config,
        "rate_limiter": RateLimiter(default_rate_per_min=600),
        "prefs": prefs,
        "now": lambda: datetime(2026, 6, 4, 12, 0, tzinfo=UTC),
    }
    return ctx


@pytest.mark.asyncio
async def test_notifies_on_new_event_same_status() -> None:
    parcel = Parcel(tracking_number="FAKE1", user_id=7, status=ShipmentStatus.IN_TRANSIT)
    ev = TrackingEvent(
        time="2026-06-04T10:00:00Z", description="Arrived at hub", location="Roma, Italy"
    )
    result = TrackingResult(
        tracking_number="FAKE1",
        found=True,
        status=ShipmentStatus.IN_TRANSIT,
        last_event="Arrived at hub",
        last_location="Roma, Italy",
        events=[ev],
    )
    ctx = _ctx(parcel, result, new_events=[ev])
    await check_updates(ctx)
    ctx.bot_data["notifier"].send_events_update.assert_awaited_once()


@pytest.mark.asyncio
async def test_no_notify_when_no_new_events_and_no_change() -> None:
    parcel = Parcel(tracking_number="FAKE1", user_id=7, status=ShipmentStatus.IN_TRANSIT)
    result = TrackingResult(
        tracking_number="FAKE1",
        found=True,
        status=ShipmentStatus.IN_TRANSIT,
        last_event="x",
        events=[],
    )
    ctx = _ctx(parcel, result, new_events=[])
    await check_updates(ctx)
    ctx.bot_data["notifier"].send_events_update.assert_not_awaited()
