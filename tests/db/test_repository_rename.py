from __future__ import annotations

import pytest

from parcel_tracker.db.migrations import init_schema
from parcel_tracker.db.models import Parcel
from parcel_tracker.db.repository import ParcelRepository


@pytest.mark.asyncio
async def test_rename_updates_name_for_owner(tmp_path) -> None:
    db = str(tmp_path / "t.db")
    await init_schema(db)
    repo = ParcelRepository(db)
    await repo.create(Parcel(tracking_number="TN1", user_id=10, name="old"))
    ok = await repo.rename("TN1", user_id=10, name="new name")
    assert ok is True
    p = await repo.get_for_user("TN1", user_id=10)
    assert p is not None and p.name == "new name"


@pytest.mark.asyncio
async def test_rename_rejects_non_owner(tmp_path) -> None:
    db = str(tmp_path / "t.db")
    await init_schema(db)
    repo = ParcelRepository(db)
    await repo.create(Parcel(tracking_number="TN1", user_id=10, name="old"))
    ok = await repo.rename("TN1", user_id=999, name="hacked")
    assert ok is False
    p = await repo.get_for_user("TN1", user_id=10)
    assert p is not None and p.name == "old"
