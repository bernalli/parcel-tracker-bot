"""Tests for repository statistics aggregates."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from parcel_tracker.db.health_repository import HealthRepository
from parcel_tracker.db.migrations import init_schema
from parcel_tracker.db.models import Parcel, TrackingEvent
from parcel_tracker.db.repository import ParcelRepository


@pytest.mark.asyncio
async def test_count_events_for_user(tmp_path: Path) -> None:
    db = str(tmp_path / "t.db")
    await init_schema(db)
    repo = ParcelRepository(db)
    await repo.create(Parcel(tracking_number="TN1", user_id=10))
    await repo.add_events_dedup(
        "TN1",
        [TrackingEvent(time="t1", description="a"), TrackingEvent(time="t2", description="b")],
    )
    assert await repo.count_events_for_user(user_id=10) == 2
    assert await repo.count_events_for_user(user_id=999) == 0


@pytest.mark.asyncio
async def test_count_quarantined(tmp_path: Path) -> None:
    db = str(tmp_path / "t.db")
    await init_schema(db)
    health = HealthRepository(db)
    future = datetime.now(UTC) + timedelta(hours=1)
    past = datetime.now(UTC) - timedelta(hours=1)
    await health.set_quarantine("ups", "", future)
    await health.set_quarantine("dhl", "", past)  # expired → not counted
    assert await health.count_quarantined() == 1
