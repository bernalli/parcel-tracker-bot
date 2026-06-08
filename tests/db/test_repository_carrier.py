from __future__ import annotations

import pytest

from parcel_tracker.db.migrations import init_schema
from parcel_tracker.db.models import Parcel
from parcel_tracker.db.repository import ParcelRepository


@pytest.mark.asyncio
async def test_update_carrier_persists_code_and_name(tmp_path) -> None:
    db = str(tmp_path / "t.db")
    await init_schema(db)
    repo = ParcelRepository(db)
    # Created without a carrier — the "Corriere: ?" case in the detail card.
    await repo.create(Parcel(tracking_number="TN1", user_id=10))

    await repo.update_carrier("TN1", "brt", "BRT")

    p = await repo.get_by_tracking_number("TN1")
    assert p is not None
    assert p.carrier_code == "brt"
    assert p.carrier_name == "BRT"
