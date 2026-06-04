import pytest

from parcel_tracker.db.migrations import init_schema
from parcel_tracker.db.models import Parcel, ShipmentStatus
from parcel_tracker.db.repository import ParcelRepository


@pytest.mark.asyncio
async def test_get_for_user_scopes_by_owner(tmp_db_path) -> None:
    await init_schema(str(tmp_db_path))
    repo = ParcelRepository(str(tmp_db_path))
    await repo.create(Parcel(tracking_number="TN1", user_id=7, status=ShipmentStatus.IN_TRANSIT))
    assert await repo.get_for_user("TN1", user_id=7) is not None
    assert await repo.get_for_user("TN1", user_id=999) is None
