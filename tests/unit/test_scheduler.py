"""Tests for core.scheduler — check_updates periodic job."""

from __future__ import annotations

import re
from datetime import UTC, datetime
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from parcel_tracker.core.rate_limiter import RateLimiter
from parcel_tracker.core.scheduler import check_updates, sort_by_priority
from parcel_tracker.core.tracker_base import AbstractTracker, TrackingResult
from parcel_tracker.db.models import Parcel, ShipmentStatus, TrackingEvent


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
    parcel_repo.set_last_check_at = AsyncMock()
    parcel_repo.add_events_dedup = AsyncMock(return_value=[])
    parcel_repo.update_latest = AsyncMock()
    parcel_repo.set_delivered = AsyncMock()

    user_repo = MagicMock()
    user_repo.get_allowed_user_ids = AsyncMock(return_value=[42] if user_ids is None else user_ids)

    health = MagicMock()
    health.is_quarantined = AsyncMock(return_value=is_quarantined)
    health.record_success = AsyncMock()
    health.record_failure = AsyncMock()

    notifier = MagicMock()
    notifier.send_status_update = AsyncMock()
    notifier.send_events_update = AsyncMock()
    notifier.send_delivery_confirmation = AsyncMock()

    config = MagicMock()
    config.batch_size = 10
    config.owner_id = 42
    config.allowed_user_ids = []

    prefs = MagicMock()
    prefs.is_allowed = AsyncMock(return_value=True)
    prefs.is_status_enabled = AsyncMock(return_value=True)
    prefs.mark_sent = AsyncMock()

    fixed_now = datetime(2026, 5, 9, 12, 0, tzinfo=UTC)

    ctx = MagicMock()
    ctx.bot_data = {
        "parcel_repo": parcel_repo,
        "registry": MagicMock(),
        "detector": detector,
        "health": health,
        "notifier": notifier,
        "user_repo": user_repo,
        "config": config,
        "rate_limiter": RateLimiter(default_rate_per_min=600),
        "prefs": prefs,
        "now": lambda: fixed_now,
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
    """With no allowed users, no owner, and no env allow-list, nothing is fetched."""
    ctx = _make_context(parcels=[], user_ids=[])
    ctx.bot_data["config"].owner_id = None
    ctx.bot_data["config"].allowed_user_ids = []
    await check_updates(ctx)
    ctx.bot_data["parcel_repo"].list_active_for_user.assert_not_called()


@pytest.mark.asyncio
async def test_check_updates_no_parcels_for_user() -> None:
    """When the user has no active parcels, nothing is fetched."""
    ctx = _make_context(parcels=[])
    await check_updates(ctx)
    ctx.bot_data["health"].is_quarantined.assert_not_called()


@pytest.mark.asyncio
async def test_check_updates_checks_owner_parcels_when_allowlist_empty() -> None:
    """Regression: the owner's parcels are checked even when the allowed_users DB
    table is empty.

    The owner is authorised via OWNER_ID and is never inserted into the
    allowed_users table, so iterating that table alone (the old behaviour) skipped
    the owner's parcels entirely — no status update or delivery notification ever
    fired for the bot's primary user.
    """
    parcel = _make_parcel(status=ShipmentStatus.IN_TRANSIT)  # user_id=42
    result = TrackingResult(
        tracking_number="FAKE123",
        found=True,
        status=ShipmentStatus.DELIVERED,
    )
    ctx = _make_context(parcels=[parcel], tracker_result=result, user_ids=[])
    ctx.bot_data["config"].owner_id = 42  # owner == the parcel's user
    ctx.bot_data["config"].allowed_user_ids = []

    await check_updates(ctx)

    ctx.bot_data["parcel_repo"].list_active_for_user.assert_awaited_with(user_id=42)
    ctx.bot_data["parcel_repo"].update_status.assert_awaited_once_with(
        "FAKE123", ShipmentStatus.DELIVERED
    )
    # DELIVERED transition hands off to the delivery-confirmation flow.
    ctx.bot_data["notifier"].send_delivery_confirmation.assert_awaited_once()
    ctx.bot_data["notifier"].send_events_update.assert_not_awaited()


@pytest.mark.asyncio
async def test_check_updates_checks_env_allowed_user_parcels() -> None:
    """Parcels owned by an env-configured ALLOWED_USER_IDS user are checked even when
    the owner differs and the allowed_users DB table is empty."""
    parcel = Parcel(
        tracking_number="FAKE123",
        user_id=777,
        name="Pacco",
        status=ShipmentStatus.IN_TRANSIT,
    )
    result = TrackingResult(
        tracking_number="FAKE123",
        found=True,
        status=ShipmentStatus.DELIVERED,
    )
    ctx = _make_context(parcels=[parcel], tracker_result=result, user_ids=[])
    ctx.bot_data["config"].owner_id = 1  # owner is someone else
    ctx.bot_data["config"].allowed_user_ids = [777]
    # Realistic per-user fetch: only user 777 owns the parcel.
    ctx.bot_data["parcel_repo"].list_active_for_user = AsyncMock(
        side_effect=lambda *, user_id: [parcel] if user_id == 777 else []
    )

    await check_updates(ctx)

    ctx.bot_data["parcel_repo"].update_status.assert_awaited_once_with(
        "FAKE123", ShipmentStatus.DELIVERED
    )
    # DELIVERED transition hands off to the delivery-confirmation flow.
    ctx.bot_data["notifier"].send_delivery_confirmation.assert_awaited_once()
    call_kwargs = ctx.bot_data["notifier"].send_delivery_confirmation.call_args.kwargs
    assert call_kwargs["chat_id"] == 777


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
    """A non-delivered status change calls update_status and notifies via
    send_events_update with status_changed=True and old/new status set."""
    parcel = _make_parcel(status=ShipmentStatus.IN_TRANSIT)
    result = TrackingResult(
        tracking_number="FAKE123",
        found=True,
        status=ShipmentStatus.OUT_FOR_DELIVERY,
    )
    ctx = _make_context(parcels=[parcel], tracker_result=result)

    await check_updates(ctx)

    ctx.bot_data["parcel_repo"].update_status.assert_called_once_with(
        "FAKE123", ShipmentStatus.OUT_FOR_DELIVERY
    )
    ctx.bot_data["notifier"].send_events_update.assert_called_once()
    ctx.bot_data["notifier"].send_delivery_confirmation.assert_not_called()
    call_kwargs: dict[str, Any] = ctx.bot_data["notifier"].send_events_update.call_args.kwargs
    assert call_kwargs["old_status"] == ShipmentStatus.IN_TRANSIT
    assert call_kwargs["new_status"] == ShipmentStatus.OUT_FOR_DELIVERY
    assert call_kwargs["status_changed"] is True
    assert call_kwargs["chat_id"] == 42


@pytest.mark.asyncio
async def test_check_updates_skips_parcels_not_due() -> None:
    """Parcels with last_check_at within their status interval are skipped."""
    from datetime import timedelta

    fixed_now = datetime(2026, 5, 9, 12, 0, tzinfo=UTC)
    fresh = Parcel(
        tracking_number="FAKE-FRESH",
        user_id=42,
        status=ShipmentStatus.IN_TRANSIT,
        last_check_at=fixed_now - timedelta(minutes=5),
    )
    stale = Parcel(
        tracking_number="FAKE-STALE",
        user_id=42,
        status=ShipmentStatus.IN_TRANSIT,
        last_check_at=fixed_now - timedelta(minutes=20),
    )
    ctx = _make_context(parcels=[fresh, stale])
    fake_tracker = ctx.bot_data["detector"].detect.return_value[0]
    fake_tracker.fetch = AsyncMock(  # type: ignore[method-assign]
        return_value=TrackingResult(
            tracking_number="X",
            found=True,
            status=ShipmentStatus.IN_TRANSIT,
        )
    )

    await check_updates(ctx)

    fake_tracker.fetch.assert_awaited_once_with("FAKE-STALE")


@pytest.mark.asyncio
async def test_check_updates_skips_delivered_parcels() -> None:
    """DELIVERED parcels have interval=0 → never due → never fetched."""
    fixed_now = datetime(2026, 5, 9, 12, 0, tzinfo=UTC)
    delivered = Parcel(
        tracking_number="FAKE-DONE",
        user_id=42,
        status=ShipmentStatus.DELIVERED,
        last_check_at=None,  # never checked, but interval=0 still wins
    )
    ctx = _make_context(parcels=[delivered])
    ctx.bot_data["now"] = lambda: fixed_now

    await check_updates(ctx)

    ctx.bot_data["detector"].detect.assert_not_called()
    ctx.bot_data["parcel_repo"].set_last_check_at.assert_not_called()


@pytest.mark.asyncio
async def test_check_updates_increments_check_total_counter() -> None:
    """A successful check bumps CHECK_TOTAL{tracker,outcome=success}."""
    from parcel_tracker.observability.metrics import CHECK_TOTAL

    parcel = _make_parcel()
    ctx = _make_context(parcels=[parcel])
    fake_tracker = ctx.bot_data["detector"].detect.return_value[0]
    # Make the tracker name unique to this test so before/after counters are isolated.
    fake_tracker.name = "metrictest_t14"

    before = CHECK_TOTAL.labels(tracker="metrictest_t14", outcome="success")._value.get()
    await check_updates(ctx)
    after = CHECK_TOTAL.labels(tracker="metrictest_t14", outcome="success")._value.get()
    assert after == before + 1.0


@pytest.mark.asyncio
async def test_check_updates_processes_batch_in_parallel() -> None:
    """Two due parcels with same tracker run via asyncio.gather (both fetched)."""
    parcels = [
        Parcel(
            tracking_number=f"FAKE-T{i}",
            user_id=42,
            status=ShipmentStatus.IN_TRANSIT,
            last_check_at=None,  # always due
        )
        for i in range(2)
    ]
    ctx = _make_context(parcels=parcels)
    fake_tracker = ctx.bot_data["detector"].detect.return_value[0]
    fake_tracker.fetch = AsyncMock(  # type: ignore[method-assign]
        return_value=TrackingResult(
            tracking_number="X",
            found=True,
            status=ShipmentStatus.IN_TRANSIT,
        )
    )

    await check_updates(ctx)

    assert fake_tracker.fetch.await_count == 2
    assert ctx.bot_data["parcel_repo"].set_last_check_at.await_count == 2


@pytest.mark.asyncio
async def test_check_updates_prefs_none_notifies_without_gating() -> None:
    """When bot_data has no 'prefs' key, an event-only notification still goes
    through (gating bypassed when prefs is None)."""
    parcel = _make_parcel(status=ShipmentStatus.IN_TRANSIT)
    ev = TrackingEvent(time="2026-05-09T11:00:00Z", description="Arrived", location="Hub")
    result = TrackingResult(
        tracking_number="FAKE123",
        found=True,
        status=ShipmentStatus.IN_TRANSIT,
        last_event="Arrived",
        events=[ev],
    )
    ctx = _make_context(parcels=[parcel], tracker_result=result)
    # New events are present so a notification is warranted even without a status change.
    ctx.bot_data["parcel_repo"].add_events_dedup = AsyncMock(return_value=[ev])
    # Remove 'prefs' to exercise the get(...) → None path
    del ctx.bot_data["prefs"]

    await check_updates(ctx)

    # Notification must still go through (gating bypassed when prefs is None)
    ctx.bot_data["notifier"].send_events_update.assert_called_once()


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


@pytest.mark.asyncio
async def test_check_updates_skips_send_when_prefs_disallow() -> None:
    """When prefs.is_status_enabled returns False, notifier.send_events_update is
    NOT called, but the status change still persists."""
    from datetime import timedelta

    now = datetime(2026, 5, 9, 12, 0, tzinfo=UTC)
    parcel = Parcel(
        tracking_number="X",
        user_id=1,
        status=ShipmentStatus.IN_TRANSIT,
        last_check_at=now - timedelta(hours=1),
    )

    ev = TrackingEvent(time="2026-05-09T11:00:00Z", description="Out for delivery", location="Hub")
    parcel_repo = MagicMock()
    parcel_repo.list_active_for_user = AsyncMock(return_value=[parcel])
    parcel_repo.update_status = AsyncMock()
    parcel_repo.set_last_check_at = AsyncMock()
    parcel_repo.add_events_dedup = AsyncMock(return_value=[ev])
    parcel_repo.update_latest = AsyncMock()

    user_repo = MagicMock()
    user_repo.get_allowed_user_ids = AsyncMock(return_value=[1])

    fake_tracker = MagicMock()
    fake_tracker.name = "ft"
    fake_tracker.fetch = AsyncMock(
        return_value=TrackingResult(
            tracking_number="X",
            found=True,
            status=ShipmentStatus.OUT_FOR_DELIVERY,
            last_event="Out for delivery",
            events=[ev],
        )
    )
    detector = MagicMock()
    detector.detect = MagicMock(return_value=[fake_tracker])

    health = MagicMock()
    health.is_quarantined = AsyncMock(return_value=False)
    health.record_success = AsyncMock()

    notifier = MagicMock()
    notifier.send_events_update = AsyncMock()
    notifier.send_delivery_confirmation = AsyncMock()

    config = MagicMock()
    config.batch_size = 10
    config.owner_id = 1
    config.allowed_user_ids = []

    prefs = MagicMock()
    prefs.is_status_enabled = AsyncMock(return_value=False)  # blocked

    context = MagicMock()
    context.bot_data = {
        "parcel_repo": parcel_repo,
        "user_repo": user_repo,
        "registry": MagicMock(),
        "detector": detector,
        "health": health,
        "notifier": notifier,
        "config": config,
        "rate_limiter": RateLimiter(default_rate_per_min=600),
        "prefs": prefs,
        "now": lambda: now,
    }

    await check_updates(context)

    notifier.send_events_update.assert_not_called()
    parcel_repo.update_status.assert_awaited_once()  # status update still persists


@pytest.mark.asyncio
async def test_check_updates_notifies_event_when_status_enabled() -> None:
    """When prefs.is_status_enabled returns True and there are new events,
    send_events_update is awaited once with the enabled status."""
    from datetime import timedelta

    now = datetime(2026, 5, 9, 12, 0, tzinfo=UTC)
    parcel = Parcel(
        tracking_number="Y",
        user_id=1,
        status=ShipmentStatus.IN_TRANSIT,
        last_check_at=now - timedelta(hours=1),
    )
    ev = TrackingEvent(time="2026-05-09T11:00:00Z", description="Departed", location="Hub")
    parcel_repo = MagicMock()
    parcel_repo.list_active_for_user = AsyncMock(return_value=[parcel])
    parcel_repo.update_status = AsyncMock()
    parcel_repo.set_last_check_at = AsyncMock()
    parcel_repo.add_events_dedup = AsyncMock(return_value=[ev])
    parcel_repo.update_latest = AsyncMock()

    user_repo = MagicMock()
    user_repo.get_allowed_user_ids = AsyncMock(return_value=[1])

    fake_tracker = MagicMock()
    fake_tracker.name = "ft"
    fake_tracker.fetch = AsyncMock(
        return_value=TrackingResult(
            tracking_number="Y",
            found=True,
            status=ShipmentStatus.IN_TRANSIT,
            last_event="Departed",
            events=[ev],
        )
    )
    detector = MagicMock()
    detector.detect = MagicMock(return_value=[fake_tracker])

    health = MagicMock()
    health.is_quarantined = AsyncMock(return_value=False)
    health.record_success = AsyncMock()

    notifier = MagicMock()
    notifier.send_events_update = AsyncMock()
    notifier.send_delivery_confirmation = AsyncMock()
    config = MagicMock()
    config.batch_size = 10
    config.owner_id = 1
    config.allowed_user_ids = []
    prefs = MagicMock()
    prefs.is_status_enabled = AsyncMock(return_value=True)

    context = MagicMock()
    context.bot_data = {
        "parcel_repo": parcel_repo,
        "user_repo": user_repo,
        "registry": MagicMock(),
        "detector": detector,
        "health": health,
        "notifier": notifier,
        "config": config,
        "rate_limiter": RateLimiter(default_rate_per_min=600),
        "prefs": prefs,
        "now": lambda: now,
    }

    await check_updates(context)
    notifier.send_events_update.assert_awaited_once()
    prefs.is_status_enabled.assert_awaited_once_with(1, ShipmentStatus.IN_TRANSIT)
