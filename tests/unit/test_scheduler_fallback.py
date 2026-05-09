"""Tests for scheduler fallback iter behavior.

When matches[0] fails (raises or returns found=False) or is quarantined,
scheduler MUST try matches[1], matches[2], ... until one succeeds or list
is exhausted.
"""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from parcel_tracker.core.rate_limiter import RateLimiter
from parcel_tracker.core.scheduler import check_updates
from parcel_tracker.core.tracker_base import TrackingResult
from parcel_tracker.db.models import Parcel, ShipmentStatus, TrackingEvent


def _make_tracker_mock(
    name: str,
    *,
    fetch_result: TrackingResult | None = None,
    fetch_raises: Exception | None = None,
) -> MagicMock:
    tracker = MagicMock()
    tracker.name = name
    if fetch_raises is not None:
        tracker.fetch = AsyncMock(side_effect=fetch_raises)
    else:
        tracker.fetch = AsyncMock(return_value=fetch_result)
    return tracker


def _make_context(
    matches: list[MagicMock],
    parcel: Parcel,
    *,
    quarantined_names: set[str] | None = None,
) -> MagicMock:
    """Build a fake PTB context.bot_data dict where detector returns the given
    matches in priority order. `quarantined_names` lists tracker.name values
    that should appear quarantined.
    """
    quarantined_names = quarantined_names or set()

    detector = MagicMock()
    detector.detect.return_value = list(matches)

    parcel_repo = MagicMock()
    parcel_repo.list_active_for_user = AsyncMock(return_value=[parcel])
    parcel_repo.update_status = AsyncMock()
    parcel_repo.set_last_check_at = AsyncMock()

    user_repo = MagicMock()
    user_repo.get_allowed_user_ids = AsyncMock(return_value=[parcel.user_id])

    health = MagicMock()

    async def _is_quarantined(tracker_name: str, _tracking_id: str) -> bool:
        return tracker_name in quarantined_names

    health.is_quarantined = AsyncMock(side_effect=_is_quarantined)
    health.record_success = AsyncMock()
    health.record_failure = AsyncMock()

    notifier = MagicMock()
    notifier.send_status_update = AsyncMock()

    config = MagicMock()
    config.batch_size = 10

    prefs = MagicMock()
    prefs.is_allowed = AsyncMock(return_value=True)
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
) -> Parcel:
    return Parcel(
        tracking_number=tracking_number,
        user_id=42,
        name="Pacco",
        status=status,
    )


def _success_result(
    tracking_number: str = "FAKE123",
    new_status: ShipmentStatus = ShipmentStatus.DELIVERED,
) -> TrackingResult:
    return TrackingResult(
        tracking_number=tracking_number,
        found=True,
        carrier_name="Secondary",
        carrier_code="secondary_success",
        status=new_status,
        events=[TrackingEvent(time="2026-05-09T12:00:00", description="Delivered", location="Hub")],
        last_event="Delivered",
        last_event_time="2026-05-09T12:00:00",
    )


@pytest.mark.asyncio
async def test_fallback_when_primary_returns_not_found() -> None:
    """matches[0] returns found=False → scheduler MUST try matches[1]."""
    parcel = _make_parcel()
    primary = _make_tracker_mock(
        "primary_fail",
        fetch_result=TrackingResult(tracking_number="FAKE123", found=False),
    )
    secondary = _make_tracker_mock(
        "secondary_success",
        fetch_result=_success_result(),
    )
    ctx = _make_context([primary, secondary], parcel)

    await check_updates(ctx)

    primary.fetch.assert_awaited_once_with("FAKE123")
    secondary.fetch.assert_awaited_once_with("FAKE123")
    ctx.bot_data["parcel_repo"].update_status.assert_awaited_once_with(
        "FAKE123", ShipmentStatus.DELIVERED
    )
    ctx.bot_data["notifier"].send_status_update.assert_awaited_once()
    ctx.bot_data["health"].record_failure.assert_awaited_once_with("primary_fail", "FAKE123")
    ctx.bot_data["health"].record_success.assert_awaited_once_with("secondary_success", "FAKE123")
    ctx.bot_data["parcel_repo"].set_last_check_at.assert_awaited_once()


@pytest.mark.asyncio
async def test_fallback_when_primary_raises() -> None:
    """matches[0].fetch raises → scheduler MUST try matches[1]."""
    parcel = _make_parcel()
    primary = _make_tracker_mock(
        "primary_raises",
        fetch_raises=RuntimeError("network error"),
    )
    secondary = _make_tracker_mock(
        "secondary_success",
        fetch_result=_success_result(),
    )
    ctx = _make_context([primary, secondary], parcel)

    await check_updates(ctx)

    primary.fetch.assert_awaited_once_with("FAKE123")
    secondary.fetch.assert_awaited_once_with("FAKE123")
    ctx.bot_data["notifier"].send_status_update.assert_awaited_once()
    ctx.bot_data["health"].record_failure.assert_awaited_once_with("primary_raises", "FAKE123")
    ctx.bot_data["health"].record_success.assert_awaited_once_with("secondary_success", "FAKE123")


@pytest.mark.asyncio
async def test_fallback_skips_quarantined_primary() -> None:
    """matches[0] quarantined → scheduler MUST skip and try matches[1]."""
    parcel = _make_parcel()
    primary = _make_tracker_mock(
        "primary_quarantined",
        fetch_result=_success_result(),
    )
    secondary = _make_tracker_mock(
        "secondary_success",
        fetch_result=_success_result(),
    )
    ctx = _make_context(
        [primary, secondary],
        parcel,
        quarantined_names={"primary_quarantined"},
    )

    await check_updates(ctx)

    primary.fetch.assert_not_awaited()  # quarantined skip means fetch not called
    secondary.fetch.assert_awaited_once_with("FAKE123")
    ctx.bot_data["notifier"].send_status_update.assert_awaited_once()


@pytest.mark.asyncio
async def test_all_matches_fail_records_each_failure_and_no_notification() -> None:
    """When all matches fail, every one gets record_failure; no notification sent."""
    parcel = _make_parcel()
    primary = _make_tracker_mock(
        "primary_fail",
        fetch_result=TrackingResult(tracking_number="FAKE123", found=False),
    )
    secondary = _make_tracker_mock(
        "secondary_fail",
        fetch_result=TrackingResult(tracking_number="FAKE123", found=False),
    )
    ctx = _make_context([primary, secondary], parcel)

    await check_updates(ctx)

    primary.fetch.assert_awaited_once_with("FAKE123")
    secondary.fetch.assert_awaited_once_with("FAKE123")
    ctx.bot_data["notifier"].send_status_update.assert_not_called()
    ctx.bot_data["parcel_repo"].update_status.assert_not_called()

    failure_calls = ctx.bot_data["health"].record_failure.await_args_list
    failure_names = [call.args[0] for call in failure_calls]
    assert "primary_fail" in failure_names
    assert "secondary_fail" in failure_names

    ctx.bot_data["parcel_repo"].set_last_check_at.assert_awaited_once()


@pytest.mark.asyncio
async def test_primary_success_secondary_not_called() -> None:
    """When matches[0] succeeds, lower-priority matches MUST NOT be tried."""
    parcel = _make_parcel()
    primary = _make_tracker_mock(
        "primary_success",
        fetch_result=_success_result(),
    )
    secondary = _make_tracker_mock(
        "secondary_unused",
        fetch_result=_success_result(),
    )
    ctx = _make_context([primary, secondary], parcel)

    await check_updates(ctx)

    primary.fetch.assert_awaited_once_with("FAKE123")
    secondary.fetch.assert_not_awaited()
    ctx.bot_data["health"].record_success.assert_awaited_once_with("primary_success", "FAKE123")
    ctx.bot_data["health"].record_failure.assert_not_awaited()
    ctx.bot_data["notifier"].send_status_update.assert_awaited_once()
