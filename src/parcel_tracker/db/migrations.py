"""Database schema initialization (async via aiosqlite)."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

import aiosqlite

SCHEMA_STATEMENTS: list[str] = [
    """
    CREATE TABLE IF NOT EXISTS parcels (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        tracking_number TEXT UNIQUE NOT NULL,
        name TEXT,
        carrier_code TEXT,
        carrier_name TEXT,
        all_carriers TEXT,
        status TEXT DEFAULT 'NotFound',
        last_event TEXT,
        last_event_time TEXT,
        events_json TEXT,
        origin TEXT,
        destination TEXT,
        user_id INTEGER NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        delivered_at TIMESTAMP,
        is_active INTEGER DEFAULT 1,
        last_check_at TIMESTAMP
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS tracking_history (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        tracking_number TEXT NOT NULL,
        event_time TEXT,
        event_description TEXT,
        location TEXT,
        carrier TEXT,
        recorded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (tracking_number) REFERENCES parcels(tracking_number)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS allowed_users (
        user_id INTEGER PRIMARY KEY,
        username TEXT,
        added_by INTEGER NOT NULL,
        added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        language TEXT NOT NULL DEFAULT 'en'
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_parcels_active ON parcels(is_active, user_id)",
    "CREATE INDEX IF NOT EXISTS idx_history_tracking ON tracking_history(tracking_number)",
    """
    CREATE TABLE IF NOT EXISTS tracker_health (
        tracker_id TEXT NOT NULL,
        tracking_id TEXT NOT NULL DEFAULT '',
        last_success_at TIMESTAMP,
        last_failure_at TIMESTAMP,
        consecutive_failures INTEGER DEFAULT 0,
        consecutive_successes INTEGER DEFAULT 0,
        quarantine_until TIMESTAMP,
        total_checks INTEGER DEFAULT 0,
        total_failures INTEGER DEFAULT 0,
        PRIMARY KEY (tracker_id, tracking_id)
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_health_quarantine ON tracker_health(quarantine_until)",
    """
    CREATE TABLE IF NOT EXISTS user_notification_prefs (
        user_id INTEGER NOT NULL,
        status_value TEXT NOT NULL,
        enabled BOOLEAN NOT NULL DEFAULT 1,
        PRIMARY KEY (user_id, status_value)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS notification_cooldown_log (
        user_id INTEGER NOT NULL,
        tracking_number TEXT NOT NULL,
        status_value TEXT NOT NULL,
        sent_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
        PRIMARY KEY (user_id, tracking_number, status_value)
    )
    """,
]


async def init_schema(db_path: str) -> None:
    """Create tables and indexes if they don't exist; enable WAL mode."""
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)

    async with aiosqlite.connect(db_path) as conn:
        await conn.execute("PRAGMA journal_mode=WAL")
        for statement in SCHEMA_STATEMENTS:
            await conn.execute(statement)
        await _add_parcels_last_check_at(conn)
        await _add_allowed_users_language(conn)
        await _add_parcels_v2_columns(conn)
        await conn.commit()


async def _add_parcels_v2_columns(conn: aiosqlite.Connection) -> None:
    """Idempotent ALTER: add v0.2 parcel columns if missing (upgrade path)."""
    cursor = await conn.execute("PRAGMA table_info(parcels)")
    rows = await cursor.fetchall()
    columns = {row[1] for row in rows}
    if "last_location" not in columns:
        await conn.execute("ALTER TABLE parcels ADD COLUMN last_location TEXT")
    if "transport_mode" not in columns:
        await conn.execute("ALTER TABLE parcels ADD COLUMN transport_mode TEXT")
    if "delivery_disputed" not in columns:
        await conn.execute(
            "ALTER TABLE parcels ADD COLUMN delivery_disputed INTEGER DEFAULT 0"
        )


async def _add_allowed_users_language(conn: aiosqlite.Connection) -> None:
    """Idempotent ALTER: add allowed_users.language if missing.

    For new DBs the column is already in CREATE TABLE; this is the upgrade path
    for DBs created before item 20.
    """
    cursor = await conn.execute("PRAGMA table_info(allowed_users)")
    rows = await cursor.fetchall()
    columns = {row[1] for row in rows}
    if "language" not in columns:
        await conn.execute(
            "ALTER TABLE allowed_users ADD COLUMN language TEXT NOT NULL DEFAULT 'en'"
        )


async def _add_parcels_last_check_at(conn: aiosqlite.Connection) -> None:
    """Idempotent ALTER: add parcels.last_check_at if missing.

    For new DBs the column is already in CREATE TABLE; this is the upgrade path
    for DBs created before Phase 2.
    """
    cursor = await conn.execute("PRAGMA table_info(parcels)")
    rows = await cursor.fetchall()
    columns = {row[1] for row in rows}  # row[1] is column name
    if "last_check_at" not in columns:
        await conn.execute("ALTER TABLE parcels ADD COLUMN last_check_at TIMESTAMP")


@asynccontextmanager
async def get_connection(db_path: str) -> AsyncIterator[aiosqlite.Connection]:
    """Yield an aiosqlite connection with row_factory set to aiosqlite.Row."""
    async with aiosqlite.connect(db_path) as conn:
        conn.row_factory = aiosqlite.Row
        await conn.execute("PRAGMA journal_mode=WAL")
        yield conn
