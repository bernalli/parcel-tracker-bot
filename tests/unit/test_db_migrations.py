"""Tests for db.migrations — async schema init."""

from __future__ import annotations

from pathlib import Path

import pytest

from parcel_tracker.db.migrations import get_connection, init_schema


@pytest.mark.asyncio
async def test_init_schema_creates_tables(tmp_db_path: Path) -> None:
    await init_schema(str(tmp_db_path))

    async with get_connection(str(tmp_db_path)) as conn:
        cursor = await conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        )
        rows = await cursor.fetchall()
        names = [r[0] for r in rows]

    assert "parcels" in names
    assert "tracking_history" in names
    assert "allowed_users" in names


@pytest.mark.asyncio
async def test_init_schema_idempotent(tmp_db_path: Path) -> None:
    await init_schema(str(tmp_db_path))
    # Second call must not error
    await init_schema(str(tmp_db_path))


@pytest.mark.asyncio
async def test_journal_mode_wal(tmp_db_path: Path) -> None:
    await init_schema(str(tmp_db_path))

    async with get_connection(str(tmp_db_path)) as conn:
        cursor = await conn.execute("PRAGMA journal_mode")
        row = await cursor.fetchone()

    assert row is not None
    assert row[0].lower() == "wal"
