"""Tests for core.health — escalation thresholds + health_aware decorator."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from parcel_tracker.core.health import (
    HealthManager,
    QuarantineThresholds,
    health_aware,
)
from parcel_tracker.db.health_repository import HealthRepository
from parcel_tracker.db.migrations import init_schema


@pytest.fixture
async def health_manager(tmp_db_path: Path) -> HealthManager:
    await init_schema(str(tmp_db_path))
    repo = HealthRepository(str(tmp_db_path))
    return HealthManager(
        repo,
        thresholds=QuarantineThresholds(
            level1_failures=3,
            level1_hours=1,
            level2_failures=6,
            level2_hours=6,
            level3_failures=12,
            level3_hours=24,
        ),
    )


@pytest.mark.asyncio
async def test_3_failures_triggers_1h_quarantine(
    health_manager: HealthManager,
) -> None:
    for _ in range(3):
        await health_manager.record_failure("dhl", "ABC")

    assert await health_manager.is_quarantined("dhl", "ABC") is True
    state = await health_manager.repo.get_state("dhl", "ABC")
    assert state is not None and state.quarantine_until is not None
    delta = state.quarantine_until - datetime.now(UTC)
    # ~1 hour, allow some slack
    assert timedelta(minutes=55) <= delta <= timedelta(minutes=65)


@pytest.mark.asyncio
async def test_6_failures_triggers_6h_quarantine(
    health_manager: HealthManager,
) -> None:
    for _ in range(6):
        await health_manager.record_failure("dhl", "ABC")

    state = await health_manager.repo.get_state("dhl", "ABC")
    assert state is not None and state.quarantine_until is not None
    delta = state.quarantine_until - datetime.now(UTC)
    assert timedelta(hours=5, minutes=55) <= delta <= timedelta(hours=6, minutes=5)


@pytest.mark.asyncio
async def test_success_clears_quarantine(health_manager: HealthManager) -> None:
    for _ in range(3):
        await health_manager.record_failure("dhl", "ABC")
    assert await health_manager.is_quarantined("dhl", "ABC") is True

    await health_manager.record_success("dhl", "ABC")
    assert await health_manager.is_quarantined("dhl", "ABC") is False


@pytest.mark.asyncio
async def test_health_aware_decorator_skips_when_quarantined(
    health_manager: HealthManager,
) -> None:
    # Trigger quarantine
    for _ in range(3):
        await health_manager.record_failure("dhl", "")

    invocations: list[int] = []

    @health_aware(manager=health_manager, tracker_id="dhl")
    async def fetch(tracking_id: str) -> str:
        invocations.append(1)
        return "result"

    result = await fetch("anything")
    assert result is None
    assert invocations == []  # never called because quarantined
