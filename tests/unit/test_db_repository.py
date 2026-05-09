"""Tests for db.repository — async CRUD operations."""

from __future__ import annotations

from pathlib import Path

import pytest

from parcel_tracker.db.migrations import init_schema
from parcel_tracker.db.models import Parcel, ShipmentStatus, TrackingEvent
from parcel_tracker.db.repository import ParcelRepository, UserRepository


@pytest.fixture
async def parcel_repo(tmp_db_path: Path) -> ParcelRepository:
    await init_schema(str(tmp_db_path))
    return ParcelRepository(str(tmp_db_path))


@pytest.fixture
async def user_repo(tmp_db_path: Path) -> UserRepository:
    await init_schema(str(tmp_db_path))
    return UserRepository(str(tmp_db_path))


@pytest.mark.asyncio
async def test_add_user_returns_true_first_time(user_repo: UserRepository) -> None:
    added = await user_repo.add_user(user_id=42, added_by=1, username="alice")
    assert added is True


@pytest.mark.asyncio
async def test_add_user_returns_false_on_duplicate(user_repo: UserRepository) -> None:
    await user_repo.add_user(user_id=42, added_by=1)
    duplicate = await user_repo.add_user(user_id=42, added_by=1)
    assert duplicate is False


@pytest.mark.asyncio
async def test_remove_user(user_repo: UserRepository) -> None:
    await user_repo.add_user(user_id=42, added_by=1)
    removed = await user_repo.remove_user(42)
    assert removed is True
    ids = await user_repo.get_allowed_user_ids()
    assert 42 not in ids


@pytest.mark.asyncio
async def test_create_and_get_parcel(parcel_repo: ParcelRepository) -> None:
    parcel = Parcel(
        tracking_number="ABC123",
        user_id=1,
        carrier_name="DHL",
        status=ShipmentStatus.IN_TRANSIT,
    )
    created = await parcel_repo.create(parcel)
    assert created.tracking_number == "ABC123"

    fetched = await parcel_repo.get_by_tracking_number("ABC123")
    assert fetched is not None
    assert fetched.carrier_name == "DHL"
    assert fetched.status is ShipmentStatus.IN_TRANSIT


@pytest.mark.asyncio
async def test_list_active_for_user(parcel_repo: ParcelRepository) -> None:
    await parcel_repo.create(Parcel(tracking_number="A", user_id=1))
    await parcel_repo.create(Parcel(tracking_number="B", user_id=1))
    await parcel_repo.create(Parcel(tracking_number="C", user_id=2))

    active = await parcel_repo.list_active_for_user(user_id=1)
    numbers = [p.tracking_number for p in active]
    assert sorted(numbers) == ["A", "B"]


@pytest.mark.asyncio
async def test_update_status(parcel_repo: ParcelRepository) -> None:
    parcel = Parcel(tracking_number="X", user_id=1)
    await parcel_repo.create(parcel)

    await parcel_repo.update_status("X", ShipmentStatus.DELIVERED)
    refetched = await parcel_repo.get_by_tracking_number("X")
    assert refetched is not None
    assert refetched.status is ShipmentStatus.DELIVERED


@pytest.mark.asyncio
async def test_add_event(parcel_repo: ParcelRepository) -> None:
    await parcel_repo.create(Parcel(tracking_number="X", user_id=1))

    event = TrackingEvent(
        time="2026-05-09 10:00:00",
        description="In transit",
        location="Milano",
        carrier="DHL",
    )
    await parcel_repo.add_event("X", event)

    history = await parcel_repo.get_history("X")
    assert len(history) == 1
    assert history[0].description == "In transit"


@pytest.mark.asyncio
async def test_set_last_check_at_round_trip(parcel_repo: ParcelRepository) -> None:
    """set_last_check_at persists the timestamp and is reflected in fetch."""
    from datetime import UTC, datetime

    await parcel_repo.create(Parcel(tracking_number="LC1", user_id=1))

    when = datetime(2026, 5, 9, 12, 0, tzinfo=UTC)
    await parcel_repo.set_last_check_at("LC1", when)

    parcel = await parcel_repo.get_by_tracking_number("LC1")
    assert parcel is not None
    assert parcel.last_check_at is not None
    assert parcel.last_check_at.year == 2026
    assert parcel.last_check_at.month == 5
    assert parcel.last_check_at.day == 9
    assert parcel.last_check_at.hour == 12
