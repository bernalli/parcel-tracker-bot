"""Scheduler: stall alerts, change tracking, seller-mode delivery, admin polling.

These run against a real SQLite database with a fake tracker and a recording
notifier, so the repository queries are exercised end to end.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from typing import Any

import pytest

from parcel_tracker.core.detector import CourierDetector
from parcel_tracker.core.health import HealthManager, QuarantineThresholds
from parcel_tracker.core.rate_limiter import RateLimiter
from parcel_tracker.core.registry import TrackerRegistry
from parcel_tracker.core.scheduler import check_updates
from parcel_tracker.core.tracker_base import AbstractTracker, TrackingResult
from parcel_tracker.db.health_repository import HealthRepository
from parcel_tracker.db.migrations import init_schema
from parcel_tracker.db.models import Parcel, ShipmentStatus, TrackingEvent
from parcel_tracker.db.repository import ParcelRepository, UserRepository
from parcel_tracker.db.settings_repository import SettingsRepository

NOW = datetime(2026, 10, 9, 12, 0, tzinfo=UTC)


class _Tracker(AbstractTracker):
    name = "fake"
    priority = 50
    tracking_id_patterns = [re.compile(r"^FAKE\d+$")]

    def __init__(self) -> None:
        self.results: dict[str, TrackingResult] = {}

    async def fetch(self, tracking_id: str) -> TrackingResult:
        return self.results.get(
            tracking_id, TrackingResult(tracking_number=tracking_id, found=False)
        )


class _Notifier:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, Any]]] = []

    def __getattr__(self, name: str) -> Any:
        async def record(**kwargs: Any) -> None:
            self.calls.append((name, kwargs))

        return record

    def names(self) -> list[str]:
        return [n for n, _ in self.calls]


async def _ctx(tmp_path, *, stall_days: int = 7, admins: frozenset[int] = frozenset()):
    db = str(tmp_path / "bot.db")
    await init_schema(db)
    registry = TrackerRegistry()
    tracker = _Tracker()
    registry.register(tracker)
    repo = ParcelRepository(db)
    settings = SettingsRepository(db)
    notifier = _Notifier()
    config = SimpleNamespace(
        owner_id=1,
        allowed_user_ids=[],
        admin_user_ids=admins,
        batch_size=10,
        status_interval_overrides={},
        data_retention_days=0,
        stall_alert_days=stall_days,
    )
    bot_data: dict[str, Any] = {
        "config": config,
        "parcel_repo": repo,
        "user_repo": UserRepository(db),
        "detector": CourierDetector(registry),
        "health": HealthManager(
            HealthRepository(db), thresholds=QuarantineThresholds(3, 1, 6, 6, 12, 24)
        ),
        "notifier": notifier,
        "rate_limiter": RateLimiter(default_rate_per_min=6000),
        "settings": settings,
        "now": lambda: NOW,
    }
    return SimpleNamespace(bot_data=bot_data), repo, tracker, notifier, settings, db


async def _age(db: str, code: str, days: float) -> None:
    import aiosqlite

    from parcel_tracker.db.repository import sql_ts

    async with aiosqlite.connect(db) as conn:
        await conn.execute(
            "UPDATE parcels SET last_change_at = ?, created_at = ? WHERE tracking_number = ?",
            (sql_ts(NOW - timedelta(days=days)), sql_ts(NOW - timedelta(days=days)), code),
        )
        await conn.commit()


async def test_stall_alert_sent_once_per_stall(tmp_path) -> None:
    ctx, repo, _tracker, notifier, _settings, db = await _ctx(tmp_path)
    await repo.create(Parcel(tracking_number="FAKE1", user_id=1, status=ShipmentStatus.IN_TRANSIT))
    await repo.update_status("FAKE1", ShipmentStatus.IN_TRANSIT, user_id=1)
    await _age(db, "FAKE1", 8)
    await check_updates(ctx)
    assert notifier.names().count("send_stall_alert") == 1
    _, kwargs = next(c for c in notifier.calls if c[0] == "send_stall_alert")
    assert kwargs["days"] == 8
    assert kwargs["status"] is ShipmentStatus.IN_TRANSIT
    await check_updates(ctx)
    assert notifier.names().count("send_stall_alert") == 1  # not repeated


async def test_stall_alert_disabled_and_fresh_parcels(tmp_path) -> None:
    ctx, repo, _tracker, notifier, _settings, db = await _ctx(tmp_path, stall_days=0)
    await repo.create(Parcel(tracking_number="FAKE2", user_id=1))
    await _age(db, "FAKE2", 30)
    await check_updates(ctx)
    assert "send_stall_alert" not in notifier.names()


async def test_new_event_resets_stall_clock(tmp_path) -> None:
    ctx, repo, tracker, notifier, _settings, db = await _ctx(tmp_path)
    await repo.create(Parcel(tracking_number="FAKE3", user_id=1))
    await _age(db, "FAKE3", 10)
    tracker.results["FAKE3"] = TrackingResult(
        tracking_number="FAKE3",
        found=True,
        status=ShipmentStatus.IN_TRANSIT,
        last_event="Departed hub",
        events=[TrackingEvent(time="2026-10-09T10:00:00Z", description="Departed hub")],
    )
    await check_updates(ctx)
    parcel = await repo.get_for_user("FAKE3", user_id=1)
    assert parcel is not None
    assert parcel.last_change_at == NOW
    assert "send_stall_alert" not in notifier.names()


async def test_seller_mode_archives_on_delivery(tmp_path) -> None:
    ctx, repo, tracker, notifier, settings, _db = await _ctx(tmp_path)
    await settings.set_seller_mode(1, True)
    await repo.create(Parcel(tracking_number="FAKE4", user_id=1, recipient="Ada"))
    tracker.results["FAKE4"] = TrackingResult(
        tracking_number="FAKE4",
        found=True,
        status=ShipmentStatus.DELIVERED,
        last_event="Delivered",
        last_location="Roma",
        events=[TrackingEvent(time="2026-10-09T09:00:00Z", description="Delivered")],
    )
    await check_updates(ctx)
    assert "send_delivery_confirmation" not in notifier.names()
    _, kwargs = next(c for c in notifier.calls if c[0] == "send_delivered_notice")
    assert kwargs["recipient"] == "Ada"
    assert kwargs["location"] == "Roma"
    parcel = await repo.get_for_user("FAKE4", user_id=1)
    assert parcel is not None
    assert not parcel.is_active
    assert parcel.delivered_at == NOW
    assert parcel.status is ShipmentStatus.DELIVERED


async def test_buyer_mode_still_prompts(tmp_path) -> None:
    ctx, repo, tracker, notifier, _settings, _db = await _ctx(tmp_path)
    await repo.create(Parcel(tracking_number="FAKE5", user_id=1))
    tracker.results["FAKE5"] = TrackingResult(
        tracking_number="FAKE5", found=True, status=ShipmentStatus.DELIVERED, last_event="ok"
    )
    await check_updates(ctx)
    assert "send_delivery_confirmation" in notifier.names()
    parcel = await repo.get_for_user("FAKE5", user_id=1)
    assert parcel is not None
    assert parcel.is_active


@pytest.mark.parametrize("admin_id", [9])
async def test_admin_parcels_are_polled(tmp_path, admin_id: int) -> None:
    ctx, repo, tracker, notifier, _settings, _db = await _ctx(
        tmp_path, admins=frozenset({admin_id})
    )
    await repo.create(Parcel(tracking_number="FAKE6", user_id=admin_id))
    tracker.results["FAKE6"] = TrackingResult(
        tracking_number="FAKE6",
        found=True,
        status=ShipmentStatus.IN_TRANSIT,
        last_event="Moving",
        events=[TrackingEvent(time="2026-10-09T08:00:00Z", description="Moving")],
    )
    await check_updates(ctx)
    parcel = await repo.get_for_user("FAKE6", user_id=admin_id)
    assert parcel is not None
    assert parcel.status is ShipmentStatus.IN_TRANSIT
    assert any(kw.get("chat_id") == admin_id for _n, kw in notifier.calls)
