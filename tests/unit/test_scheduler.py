"""Tests for core.scheduler — check_updates periodic job."""

from __future__ import annotations

import re
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from parcel_tracker.core.scheduler import check_updates, sort_by_priority
from parcel_tracker.core.tracker_base import AbstractTracker, TrackingResult
from parcel_tracker.db.models import Parcel, ShipmentStatus


class _FakeTracker(AbstractTracker):
    name = "fake_tracker"
    priority = 10
    tracking_id_patterns = [re.compile(r"^FAKE\d+$")]

    def __init__(self, result: TrackingResult) -> None:
        self._result = result

    async def fetch(self, tracking_id: str) -> TrackingResult:
        return self._result


def _make_context(
    parcels: list[Parcel],
    tracker_result: TrackingResult | None = None,
    is_quarantined: bool = False,
    user_ids: list[int] | None = None,
    old_status: ShipmentStatus = ShipmentStatus.IN_TRANSIT,
) -> MagicMock:
    """Build a fake PTB context.bot_data dict."""
    tracker = _FakeTracker(
        tracker_result
        or TrackingResult(
            tracking_number="FAKE123",
            found=True,
            status=ShipmentStatus.IN_TRANSIT,
        )
    )

    detector = MagicMock()
    detector.detect.return_value = [tracker]

    parcel_repo = MagicMock()
    parcel_repo.list_active_for_user = AsyncMock(return_value=parcels)
    parcel_repo.update_status = AsyncMock()

    user_repo = MagicMock()
    user_repo.get_allowed_user_ids = AsyncMock(return_value=[42] if user_ids is None else user_ids)

    health = MagicMock()
    health.is_quarantined = AsyncMock(return_value=is_quarantined)
    health.record_success = AsyncMock()
    health.record_failure = AsyncMock()

    notifier = MagicMock()
    notifier.send_status_update = AsyncMock()

    ctx = MagicMock()
    ctx.bot_data = {
        "parcel_repo": parcel_repo,
        "registry": MagicMock(),
        "detector": detector,
        "health": health,
        "notifier": notifier,
        "user_repo": user_repo,
    }
    return ctx


def _make_parcel(
    tracking_number: str = "FAKE123",
    status: ShipmentStatus = ShipmentStatus.IN_TRANSIT,
    name: str = "Pacco",
) -> Parcel:
    return Parcel(
        tracking_number=tracking_number,
        user_id=42,
        name=name,
        status=status,
    )


@pytest.mark.asyncio
async def test_check_updates_no_users() -> None:
    """When there are no allowed users, nothing is fetched."""
    ctx = _make_context(parcels=[], user_ids=[])
    await check_updates(ctx)
    ctx.bot_data["parcel_repo"].list_active_for_user.assert_not_called()


@pytest.mark.asyncio
async def test_check_updates_no_parcels_for_user() -> None:
    """When the user has no active parcels, nothing is fetched."""
    ctx = _make_context(parcels=[])
    await check_updates(ctx)
    ctx.bot_data["health"].is_quarantined.assert_not_called()


@pytest.mark.asyncio
async def test_check_updates_no_tracker_match() -> None:
    """When detector finds no match, parcel is skipped."""
    parcel = _make_parcel()
    ctx = _make_context(parcels=[parcel])
    ctx.bot_data["detector"].detect.return_value = []  # no match

    await check_updates(ctx)

    ctx.bot_data["health"].is_quarantined.assert_not_called()
    ctx.bot_data["parcel_repo"].update_status.assert_not_called()


@pytest.mark.asyncio
async def test_check_updates_skips_quarantined_parcel() -> None:
    """When tracker is quarantined, the fetch is skipped entirely."""
    parcel = _make_parcel()
    ctx = _make_context(parcels=[parcel], is_quarantined=True)

    await check_updates(ctx)

    ctx.bot_data["health"].record_success.assert_not_called()
    ctx.bot_data["health"].record_failure.assert_not_called()
    ctx.bot_data["parcel_repo"].update_status.assert_not_called()


@pytest.mark.asyncio
async def test_check_updates_tracker_fetch_exception() -> None:
    """When tracker.fetch raises, failure is recorded and no status update occurs."""
    parcel = _make_parcel()
    tracker = MagicMock()
    tracker.name = "bad_tracker"
    tracker.fetch = AsyncMock(side_effect=RuntimeError("network error"))

    ctx = _make_context(parcels=[parcel])
    ctx.bot_data["detector"].detect.return_value = [tracker]

    await check_updates(ctx)

    ctx.bot_data["health"].record_failure.assert_called_once_with("bad_tracker", "FAKE123")
    ctx.bot_data["parcel_repo"].update_status.assert_not_called()
    ctx.bot_data["notifier"].send_status_update.assert_not_called()


@pytest.mark.asyncio
async def test_check_updates_result_not_found() -> None:
    """When result.found is False, failure is recorded and no update sent."""
    parcel = _make_parcel()
    result = TrackingResult(tracking_number="FAKE123", found=False)
    ctx = _make_context(parcels=[parcel], tracker_result=result)

    await check_updates(ctx)

    ctx.bot_data["health"].record_failure.assert_called_once()
    ctx.bot_data["parcel_repo"].update_status.assert_not_called()


@pytest.mark.asyncio
async def test_check_updates_status_unchanged_no_notification() -> None:
    """When status is the same, no update or notification is sent."""
    parcel = _make_parcel(status=ShipmentStatus.IN_TRANSIT)
    result = TrackingResult(
        tracking_number="FAKE123",
        found=True,
        status=ShipmentStatus.IN_TRANSIT,
    )
    ctx = _make_context(parcels=[parcel], tracker_result=result)

    await check_updates(ctx)

    ctx.bot_data["health"].record_success.assert_called_once()
    ctx.bot_data["parcel_repo"].update_status.assert_not_called()
    ctx.bot_data["notifier"].send_status_update.assert_not_called()


@pytest.mark.asyncio
async def test_check_updates_status_changed_sends_notification() -> None:
    """When status changes, update_status and send_status_update are called."""
    parcel = _make_parcel(status=ShipmentStatus.IN_TRANSIT)
    result = TrackingResult(
        tracking_number="FAKE123",
        found=True,
        status=ShipmentStatus.DELIVERED,
    )
    ctx = _make_context(parcels=[parcel], tracker_result=result)

    await check_updates(ctx)

    ctx.bot_data["parcel_repo"].update_status.assert_called_once_with(
        "FAKE123", ShipmentStatus.DELIVERED
    )
    ctx.bot_data["notifier"].send_status_update.assert_called_once()
    call_kwargs: dict[str, Any] = ctx.bot_data["notifier"].send_status_update.call_args.kwargs
    assert call_kwargs["old_status"] == ShipmentStatus.IN_TRANSIT
    assert call_kwargs["new_status"] == ShipmentStatus.DELIVERED
    assert call_kwargs["chat_id"] == 42


def test_sort_by_priority_orders_out_for_delivery_first() -> None:
    parcels = [
        Parcel(tracking_number="A", user_id=1, status=ShipmentStatus.IN_TRANSIT),
        Parcel(tracking_number="B", user_id=1, status=ShipmentStatus.OUT_FOR_DELIVERY),
        Parcel(tracking_number="C", user_id=1, status=ShipmentStatus.PICKUP),
    ]
    sorted_p = sort_by_priority(parcels)
    assert [p.tracking_number for p in sorted_p] == ["B", "A", "C"]


def test_sort_by_priority_preserves_unknowns_at_end() -> None:
    parcels = [
        Parcel(tracking_number="A", user_id=1, status=ShipmentStatus.NOT_FOUND),
        Parcel(tracking_number="B", user_id=1, status=ShipmentStatus.OUT_FOR_DELIVERY),
    ]
    sorted_p = sort_by_priority(parcels)
    assert sorted_p[0].tracking_number == "B"
    assert sorted_p[-1].tracking_number == "A"
