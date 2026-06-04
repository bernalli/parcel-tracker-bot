import pytest

from parcel_tracker.db.migrations import init_schema
from parcel_tracker.db.models import Parcel, ShipmentStatus, TrackingEvent
from parcel_tracker.db.repository import ParcelRepository


async def _repo(tmp_db_path) -> ParcelRepository:
    await init_schema(str(tmp_db_path))
    repo = ParcelRepository(str(tmp_db_path))
    await repo.create(Parcel(tracking_number="TN1", user_id=1, status=ShipmentStatus.IN_TRANSIT))
    return repo


@pytest.mark.asyncio
async def test_add_events_dedup_inserts_only_new(tmp_db_path) -> None:
    repo = await _repo(tmp_db_path)
    e1 = TrackingEvent(time="2026-06-01T10:00:00Z", description="Picked up", location="Milano, IT")
    e2 = TrackingEvent(time="2026-06-02T08:00:00Z", description="Departed", location="Roma, IT")
    new1 = await repo.add_events_dedup("TN1", [e1, e2])
    assert {ev.description for ev in new1} == {"Picked up", "Departed"}
    e3 = TrackingEvent(time="2026-06-03T09:00:00Z", description="Arrived", location="Torino, IT")
    new2 = await repo.add_events_dedup("TN1", [e1, e2, e3])
    assert [ev.description for ev in new2] == ["Arrived"]
    hist = await repo.get_history("TN1")
    assert len(hist) == 3


@pytest.mark.asyncio
async def test_update_latest_roundtrips(tmp_db_path) -> None:
    repo = await _repo(tmp_db_path)
    await repo.update_latest("TN1", "Out for delivery", "2026-06-03T09:00:00Z", "Torino, IT")
    p = await repo.get_by_tracking_number("TN1")
    assert p is not None
    assert p.last_event == "Out for delivery"
    assert p.last_location == "Torino, IT"


@pytest.mark.asyncio
async def test_create_returns_none_on_duplicate(tmp_db_path) -> None:
    repo = await _repo(tmp_db_path)  # already created TN1
    dup = await repo.create(Parcel(tracking_number="TN1", user_id=1))
    assert dup is None
