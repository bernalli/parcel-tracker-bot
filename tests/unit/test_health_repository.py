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
