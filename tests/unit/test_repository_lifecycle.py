from datetime import UTC, datetime

import pytest

from parcel_tracker.db.migrations import init_schema
from parcel_tracker.db.models import Parcel, ShipmentStatus
from parcel_tracker.db.repository import ParcelRepository


async def _repo(tmp_db_path) -> ParcelRepository:
    await init_schema(str(tmp_db_path))
    repo = ParcelRepository(str(tmp_db_path))
    await repo.create(Parcel(tracking_number="TN1", user_id=7, status=ShipmentStatus.IN_TRANSIT))
    return repo


@pytest.mark.asyncio
async def test_set_delivered_and_archive(tmp_db_path) -> None:
    repo = await _repo(tmp_db_path)
    when = datetime(2026, 6, 3, 12, 0, tzinfo=UTC)
    await repo.set_delivered("TN1", when)
    await repo.deactivate("TN1")
    active = await repo.list_active_for_user(user_id=7)
    assert active == []
    archived = await repo.list_archived_for_user(user_id=7)
    assert [p.tracking_number for p in archived] == ["TN1"]
    assert archived[0].status is ShipmentStatus.DELIVERED
    assert archived[0].delivered_at is not None


@pytest.mark.asyncio
async def test_archive_delivered_for_user(tmp_db_path) -> None:
    from datetime import UTC, datetime

    repo = await _repo(tmp_db_path)  # TN1 active InTransit
    await repo.set_delivered("TN1", datetime(2026, 6, 3, tzinfo=UTC))
    n = await repo.archive_delivered_for_user(user_id=7)
    assert n == 1
    assert await repo.list_active_for_user(user_id=7) == []


@pytest.mark.asyncio
async def test_disputed_roundtrip_and_reactivate(tmp_db_path) -> None:
    repo = await _repo(tmp_db_path)
    await repo.deactivate("TN1")
    await repo.reactivate("TN1")
    await repo.set_disputed("TN1", True)
    p = await repo.get_by_tracking_number("TN1")
    assert p is not None
    assert p.is_active is True
    assert p.delivery_disputed is True
