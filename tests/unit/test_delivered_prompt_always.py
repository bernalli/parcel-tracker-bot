from __future__ import annotations

import re
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from parcel_tracker.core.rate_limiter import RateLimiter
from parcel_tracker.core.scheduler import check_updates
from parcel_tracker.core.tracker_base import AbstractTracker, TrackingResult
from parcel_tracker.db.models import Parcel, ShipmentStatus


class _T(AbstractTracker):
    name = "fake"
    priority = 10
    tracking_id_patterns = [re.compile(r"^FAKE\d+$")]

    def __init__(self, r: TrackingResult) -> None:
        self._r = r

    async def fetch(self, tracking_id: str) -> TrackingResult:
        return self._r


@pytest.mark.asyncio
async def test_delivered_prompt_sent_even_when_status_disabled() -> None:
    parcel = Parcel(tracking_number="FAKE1", user_id=7, status=ShipmentStatus.OUT_FOR_DELIVERY)
    result = TrackingResult(tracking_number="FAKE1", found=True,
                            status=ShipmentStatus.DELIVERED, last_event="Delivered", events=[])
    detector = MagicMock()
    detector.detect.return_value = [_T(result)]
    repo = MagicMock()
    repo.list_active_for_user = AsyncMock(return_value=[parcel])
    repo.set_last_check_at = AsyncMock()
    repo.update_status = AsyncMock()
    repo.add_events_dedup = AsyncMock(return_value=[])
    repo.update_latest = AsyncMock()
    repo.set_delivered = AsyncMock()
    user_repo = MagicMock()
    user_repo.get_allowed_user_ids = AsyncMock(return_value=[])
    health = MagicMock()
    health.is_quarantined = AsyncMock(return_value=False)
    health.record_success = AsyncMock()
    health.record_failure = AsyncMock()
    notifier = MagicMock()
    notifier.send_delivery_confirmation = AsyncMock()
    notifier.send_events_update = AsyncMock()
    config = MagicMock()
    config.batch_size = 10
    config.owner_id = 7
    config.allowed_user_ids = []
    prefs = MagicMock()
    prefs.is_status_enabled = AsyncMock(return_value=False)  # DELIVERED muted
    ctx = MagicMock()
    ctx.bot_data = {"parcel_repo": repo, "registry": MagicMock(), "detector": detector,
                    "health": health, "notifier": notifier, "user_repo": user_repo,
                    "config": config, "rate_limiter": RateLimiter(default_rate_per_min=600),
                    "prefs": prefs, "now": lambda: datetime(2026, 6, 4, 12, 0, tzinfo=UTC)}
    await check_updates(ctx)
    notifier.send_delivery_confirmation.assert_awaited_once()  # prompt sent despite muted pref
