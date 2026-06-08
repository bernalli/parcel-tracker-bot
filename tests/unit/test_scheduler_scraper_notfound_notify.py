"""Reproduction: scraper (BRT-style) results with status=NOT_FOUND must still
notify the user about genuinely new intermediate events.

Background: Italian scraper plugins (BRT/GLS/SDA) return ``found=True`` with an
event history but leave ``TrackingResult.status`` at NOT_FOUND. The per-event
notification gate in ``_notify`` is ``is_status_enabled(final_result.status)``,
which hard-returns False for NOT_FOUND -> every intermediate event was silently
swallowed. ``_reconcile_status_and_carrier`` derives a real status from
``last_event`` and is supposed to lift this. These tests measure the *current*
behaviour empirically.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from parcel_tracker.core.rate_limiter import RateLimiter
from parcel_tracker.core.scheduler import check_updates
from parcel_tracker.core.tracker_base import AbstractTracker, TrackingResult
from parcel_tracker.db.models import Parcel, ShipmentStatus, TrackingEvent
from parcel_tracker.notifier.preferences import CooldownConfig, NotificationPreferences


class _T(AbstractTracker):
    name = "fake-scraper"
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
    repo.update_carrier = AsyncMock()
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
    # REAL preference gate, with NO explicit user prefs (get_pref -> None => default).
    pref_repo = MagicMock()
    pref_repo.get_pref = AsyncMock(return_value=None)
    prefs = NotificationPreferences(pref_repo, CooldownConfig(minutes=0))
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
        "now": lambda: datetime(2026, 6, 8, 12, 0, tzinfo=UTC),
    }
    return ctx


@pytest.mark.asyncio
async def test_scraper_notfound_with_last_event_notifies_new_event() -> None:
    """BRT-style: status NOT_FOUND but last_event set + a new intermediate event.

    reconcile should derive IN_TRANSIT and the user SHOULD be notified.
    """
    parcel = Parcel(tracking_number="FAKE1", user_id=7, status=ShipmentStatus.IN_TRANSIT)
    ev = TrackingEvent(
        time="2026-06-08T07:54:00Z", description="ARRIVED AT DEPOT", location="LECCO"
    )
    result = TrackingResult(
        tracking_number="FAKE1",
        found=True,
        status=ShipmentStatus.NOT_FOUND,  # scraper leaves it at default
        last_event="ARRIVED AT DEPOT",
        last_location="LECCO",
        events=[ev],
    )
    ctx = _ctx(parcel, result, new_events=[ev])
    await check_updates(ctx)
    ctx.bot_data["notifier"].send_events_update.assert_awaited_once()


@pytest.mark.asyncio
async def test_scraper_notfound_without_last_event_still_notifies_new_event() -> None:
    """Residual hole: status NOT_FOUND, new events present, but last_event is None.

    reconcile cannot derive a status -> stays NOT_FOUND -> is_status_enabled False.
    A genuine new event must NOT be silently dropped.
    """
    parcel = Parcel(tracking_number="FAKE1", user_id=7, status=ShipmentStatus.IN_TRANSIT)
    ev = TrackingEvent(
        time="2026-06-08T07:54:00Z", description="ARRIVED AT DEPOT", location="LECCO"
    )
    result = TrackingResult(
        tracking_number="FAKE1",
        found=True,
        status=ShipmentStatus.NOT_FOUND,
        last_event=None,  # no denormalised last_event
        events=[ev],
    )
    ctx = _ctx(parcel, result, new_events=[ev])
    await check_updates(ctx)
    ctx.bot_data["notifier"].send_events_update.assert_awaited_once()
