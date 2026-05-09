"""Tests for db.health_repository."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from parcel_tracker.db.health_repository import HealthRepository
from parcel_tracker.db.migrations import init_schema


@pytest.fixture
async def health_repo(tmp_db_path: Path) -> HealthRepository:
    await init_schema(str(tmp_db_path))
    return HealthRepository(str(tmp_db_path))


@pytest.mark.asyncio
async def test_record_success_resets_consecutive_failures(
    health_repo: HealthRepository,
) -> None:
    await health_repo.record_failure("dhl", "ABC")
    await health_repo.record_failure("dhl", "ABC")
    await health_repo.record_success("dhl", "ABC")

    state = await health_repo.get_state("dhl", "ABC")
    assert state is not None
    assert state.consecutive_failures == 0
    assert state.consecutive_successes == 1


@pytest.mark.asyncio
async def test_record_failure_increments(health_repo: HealthRepository) -> None:
    await health_repo.record_failure("dhl", "ABC")
    await health_repo.record_failure("dhl", "ABC")
    state = await health_repo.get_state("dhl", "ABC")
    assert state is not None
    assert state.consecutive_failures == 2


@pytest.mark.asyncio
async def test_set_quarantine(health_repo: HealthRepository) -> None:
    until = datetime.now(UTC) + timedelta(hours=1)
    await health_repo.set_quarantine("dhl", "ABC", until)

    is_quarantined = await health_repo.is_quarantined("dhl", "ABC")
    assert is_quarantined is True


@pytest.mark.asyncio
async def test_quarantine_expires(health_repo: HealthRepository) -> None:
    past = datetime.now(UTC) - timedelta(hours=1)
    await health_repo.set_quarantine("dhl", "ABC", past)

    is_quarantined = await health_repo.is_quarantined("dhl", "ABC")
    assert is_quarantined is False


@pytest.mark.asyncio
async def test_health_repository_iter_global_states_returns_only_global(tmp_path: Path) -> None:
    db_path = str(tmp_path / "h.db")
    await init_schema(db_path)
    repo = HealthRepository(db_path)

    await repo.record_success("dhl", "")  # global
    await repo.record_success("dhl", "AB123")  # per-shipment
    await repo.record_success("track17", "")  # global

    states = [s async for s in repo.iter_global_states()]
    tracker_ids = sorted(s.tracker_id for s in states)
    assert tracker_ids == ["dhl", "track17"]
    for s in states:
        assert s.tracking_id == ""


@pytest.mark.asyncio
async def test_health_repository_reset_tracker_clears_all_entries(tmp_path: Path) -> None:
    db_path = str(tmp_path / "h.db")
    await init_schema(db_path)
    repo = HealthRepository(db_path)

    # Build up consecutive_successes so the post-reset assertion is meaningful
    await repo.record_success("dhl", "")  # global
    await repo.record_success("dhl", "")
    await repo.record_success("dhl", "AB123")

    for _ in range(3):
        await repo.record_failure("dhl", "")
        await repo.record_failure("dhl", "AB123")
    until = datetime.now(UTC) + timedelta(hours=1)
    await repo.set_quarantine("dhl", "", until)
    await repo.set_quarantine("dhl", "AB123", until)

    await repo.reset_tracker("dhl")

    state_global = await repo.get_state("dhl", "")
    state_ship = await repo.get_state("dhl", "AB123")
    assert state_global is not None
    assert state_global.consecutive_failures == 0
    assert state_global.consecutive_successes == 0
    assert state_global.quarantine_until is None
    assert state_ship is not None
    assert state_ship.consecutive_failures == 0
    assert state_ship.consecutive_successes == 0
    assert state_ship.quarantine_until is None


@pytest.mark.asyncio
async def test_health_repository_reset_tracker_no_rows_is_noop(tmp_path: Path) -> None:
    """reset_tracker on an unknown tracker must not raise (UPDATE WHERE = 0 rows = no-op)."""
    db_path = str(tmp_path / "h.db")
    await init_schema(db_path)
    repo = HealthRepository(db_path)

    # Must complete without raising
    await repo.reset_tracker("nonexistent_tracker")
