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


def _ctx(parcel: Parcel, result: TrackingResult) -> MagicMock:
    detector = MagicMock()
    detector.detect.return_value = [_T(result)]
    repo = MagicMock()
    repo.list_active_for_user = AsyncMock(return_value=[parcel])
    repo.set_last_check_at = AsyncMock()
    repo.update_status = AsyncMock()
    repo.add_events_dedup = AsyncMock(return_value=result.events)
    repo.update_latest = AsyncMock()
    repo.update_carrier = AsyncMock()
    user_repo = MagicMock()
    user_repo.get_allowed_user_ids = AsyncMock(return_value=[])
    health = MagicMock()
    health.is_quarantined = AsyncMock(return_value=False)
    health.record_success = AsyncMock()
    health.record_failure = AsyncMock()
    notifier = MagicMock()
    notifier.send_status_update = AsyncMock()
    config = MagicMock()
    config.batch_size = 10
    config.owner_id = 7
    config.allowed_user_ids = []
    prefs = MagicMock()
    prefs.is_allowed = AsyncMock(return_value=True)
    prefs.mark_sent = AsyncMock()
    prefs.is_status_enabled = AsyncMock(return_value=False)
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
async def test_scheduler_persists_events_and_latest() -> None:
    parcel = Parcel(tracking_number="FAKE1", user_id=7, status=ShipmentStatus.IN_TRANSIT)
    ev = TrackingEvent(
        time="2026-06-04T10:00:00Z", description="Departed", location="Milano, Italy"
    )
    result = TrackingResult(
        tracking_number="FAKE1",
        found=True,
        status=ShipmentStatus.IN_TRANSIT,
        last_event="Departed",
        last_event_time="2026-06-04T10:00:00Z",
        last_location="Milano, Italy",
        events=[ev],
    )
    ctx = _ctx(parcel, result)
    await check_updates(ctx)
    ctx.bot_data["parcel_repo"].add_events_dedup.assert_awaited_once()
    ctx.bot_data["parcel_repo"].update_latest.assert_awaited_once_with(
        "FAKE1", "Departed", "2026-06-04T10:00:00Z", "Milano, Italy"
    )


@pytest.mark.asyncio
async def test_scheduler_derives_status_when_tracker_omits_it() -> None:
    # BRT-style result: found with events + carrier, but status left at the
    # NOT_FOUND default (the live bug). Scheduler must recover status from the
    # latest event and persist the carrier learned during the fetch.
    parcel = Parcel(tracking_number="FAKE9", user_id=7, status=ShipmentStatus.NOT_FOUND)
    ev = TrackingEvent(time="08.06.2026 07.54", description="ARRIVED AT DEPOT")
    result = TrackingResult(
        tracking_number="FAKE9",
        found=True,
        carrier_code="brt",
        carrier_name="BRT",
        last_event="ARRIVED AT DEPOT",
        last_event_time="08.06.2026 07.54",
        events=[ev],
    )  # status intentionally left at its NOT_FOUND default
    ctx = _ctx(parcel, result)
    await check_updates(ctx)
    repo = ctx.bot_data["parcel_repo"]
    repo.update_status.assert_awaited_once_with("FAKE9", ShipmentStatus.IN_TRANSIT)
    repo.update_carrier.assert_awaited_once_with("FAKE9", "brt", "BRT")


@pytest.mark.asyncio
async def test_scheduler_skips_carrier_update_when_unchanged() -> None:
    parcel = Parcel(
        tracking_number="FAKE8",
        user_id=7,
        status=ShipmentStatus.IN_TRANSIT,
        carrier_code="brt",
        carrier_name="BRT",
    )
    ev = TrackingEvent(time="x", description="In transito")
    result = TrackingResult(
        tracking_number="FAKE8",
        found=True,
        status=ShipmentStatus.IN_TRANSIT,
        carrier_code="brt",
        carrier_name="BRT",
        last_event="In transito",
        events=[ev],
    )
    ctx = _ctx(parcel, result)
    await check_updates(ctx)
    ctx.bot_data["parcel_repo"].update_carrier.assert_not_awaited()
