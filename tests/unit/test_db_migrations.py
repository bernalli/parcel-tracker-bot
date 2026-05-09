"""Tests for db.migrations — async schema init."""

from __future__ import annotations

from pathlib import Path

import aiosqlite
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


@pytest.mark.asyncio
async def test_init_schema_adds_last_check_at_column(tmp_db_path: Path) -> None:
    """parcels.last_check_at column must exist after init_schema."""
    await init_schema(str(tmp_db_path))
    async with get_connection(str(tmp_db_path)) as conn:
        cursor = await conn.execute("PRAGMA table_info(parcels)")
        rows = await cursor.fetchall()
        columns = [row["name"] for row in rows]
    assert "last_check_at" in columns


@pytest.mark.asyncio
async def test_init_schema_idempotent_on_last_check_at(tmp_db_path: Path) -> None:
    """Re-running init_schema must not error if last_check_at already exists."""
    await init_schema(str(tmp_db_path))
    await init_schema(str(tmp_db_path))  # should not raise
    async with get_connection(str(tmp_db_path)) as conn:
        cursor = await conn.execute("PRAGMA table_info(parcels)")
        rows = await cursor.fetchall()
        columns = [row["name"] for row in rows]
    assert columns.count("last_check_at") == 1


@pytest.mark.asyncio
async def test_init_schema_creates_user_notification_prefs(tmp_path) -> None:
    db_path = str(tmp_path / "n.db")
    await init_schema(db_path)
    async with aiosqlite.connect(db_path) as conn:
        cursor = await conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='user_notification_prefs'"
        )
        row = await cursor.fetchone()
    assert row is not None


@pytest.mark.asyncio
async def test_init_schema_creates_notification_cooldown_log(tmp_path) -> None:
    db_path = str(tmp_path / "n.db")
    await init_schema(db_path)
    async with aiosqlite.connect(db_path) as conn:
        cursor = await conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='notification_cooldown_log'"
        )
        row = await cursor.fetchone()
    assert row is not None


@pytest.mark.asyncio
async def test_init_schema_idempotent_for_notification_tables(tmp_path) -> None:
    db_path = str(tmp_path / "n.db")
    await init_schema(db_path)
    await init_schema(db_path)  # must not raise
