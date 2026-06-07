from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock

import pytest

from parcel_tracker.core import scheduler
from parcel_tracker.core.tracker_base import TrackingResult
from parcel_tracker.db.models import Parcel, ShipmentStatus


class _FakeTracker:
    name = "fake"
    priority = 5

    def __init__(self, result: TrackingResult | None = None, exc: Exception | None = None):
        self._result = result
        self._exc = exc

    async def fetch(self, tn: str) -> TrackingResult:
        if self._exc:
            raise self._exc
        assert self._result is not None
        return self._result


class _FakeDetector:
    def __init__(self, trackers: list) -> None:
        self._trackers = trackers

    def detect(self, tn: str) -> list:
        return self._trackers


def _bot_data(tracker, *, quarantined: bool = False) -> dict:
    health = AsyncMock()
    health.is_quarantined.return_value = quarantined
    rate = AsyncMock()
    repo = AsyncMock()
    repo.add_events_dedup.return_value = []
    return {
        "parcel_repo": repo,
        "detector": _FakeDetector([tracker] if tracker else []),
        "health": health,
        "notifier": AsyncMock(),
        "rate_limiter": rate,
        "prefs": None,
        "now": lambda: datetime(2026, 6, 7, tzinfo=UTC),
    }


def _parcel() -> Parcel:
    return Parcel(tracking_number="TN1", user_id=10, status=ShipmentStatus.IN_TRANSIT)


@pytest.mark.asyncio
async def test_check_parcel_now_returns_none_for_foreign_parcel() -> None:
    bd = _bot_data(None)
    bd["parcel_repo"].get_for_user.return_value = None
    outcome = await scheduler.check_parcel_now(bd, user_id=10, tracking_number="TN1")
    assert outcome is None


@pytest.mark.asyncio
async def test_check_parcel_now_quarantined_outcome() -> None:
    tracker = _FakeTracker(
        result=TrackingResult(tracking_number="TN1", found=True, status=ShipmentStatus.IN_TRANSIT)
    )
    bd = _bot_data(tracker, quarantined=True)
    bd["parcel_repo"].get_for_user.return_value = _parcel()
    outcome = await scheduler.check_parcel_now(bd, user_id=10, tracking_number="TN1")
    assert outcome == "quarantined"


@pytest.mark.asyncio
async def test_check_parcel_now_failed_outcome() -> None:
    tracker = _FakeTracker(exc=RuntimeError("boom"))
    bd = _bot_data(tracker)
    bd["parcel_repo"].get_for_user.return_value = _parcel()
    outcome = await scheduler.check_parcel_now(bd, user_id=10, tracking_number="TN1")
    assert outcome == "failed"


@pytest.mark.asyncio
async def test_check_parcel_now_updates_without_notifying() -> None:
    result = TrackingResult(
        tracking_number="TN1",
        found=True,
        status=ShipmentStatus.OUT_FOR_DELIVERY,
        last_event="On the way",
    )
    tracker = _FakeTracker(result=result)
    bd = _bot_data(tracker)
    bd["parcel_repo"].get_for_user.return_value = _parcel()
    outcome = await scheduler.check_parcel_now(bd, user_id=10, tracking_number="TN1")
    assert outcome == "updated"  # status changed
    bd["parcel_repo"].update_status.assert_awaited()  # persistito
    bd["notifier"].send_events_update.assert_not_awaited()  # MAI notifiche da refresh manuale


@pytest.mark.asyncio
async def test_check_parcel_now_delivered_still_sends_confirmation() -> None:
    result = TrackingResult(tracking_number="TN1", found=True, status=ShipmentStatus.DELIVERED)
    tracker = _FakeTracker(result=result)
    bd = _bot_data(tracker)
    bd["parcel_repo"].get_for_user.return_value = _parcel()
    outcome = await scheduler.check_parcel_now(bd, user_id=10, tracking_number="TN1")
    assert outcome == "delivered"
    bd["notifier"].send_delivery_confirmation.assert_awaited()  # lifecycle, mai perso
