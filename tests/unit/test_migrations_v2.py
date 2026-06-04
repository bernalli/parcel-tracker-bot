import aiosqlite
import pytest

from parcel_tracker.db.migrations import init_schema


@pytest.mark.asyncio
async def test_parcels_has_new_columns(tmp_db_path) -> None:
    db = str(tmp_db_path)
    await init_schema(db)
    async with aiosqlite.connect(db) as conn:
        cur = await conn.execute("PRAGMA table_info(parcels)")
        cols = {row[1] for row in await cur.fetchall()}
    assert {"last_location", "transport_mode", "delivery_disputed"} <= cols


@pytest.mark.asyncio
async def test_init_schema_idempotent(tmp_db_path) -> None:
    db = str(tmp_db_path)
    await init_schema(db)
    await init_schema(db)  # second run must not raise
