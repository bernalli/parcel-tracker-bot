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
        is_active INTEGER DEFAULT 1
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
        added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
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
]


async def init_schema(db_path: str) -> None:
    """Create tables and indexes if they don't exist; enable WAL mode."""
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)

    async with aiosqlite.connect(db_path) as conn:
        await conn.execute("PRAGMA journal_mode=WAL")
        for statement in SCHEMA_STATEMENTS:
            await conn.execute(statement)
        await conn.commit()


@asynccontextmanager
async def get_connection(db_path: str) -> AsyncIterator[aiosqlite.Connection]:
    """Yield an aiosqlite connection with row_factory set to aiosqlite.Row."""
    async with aiosqlite.connect(db_path) as conn:
        conn.row_factory = aiosqlite.Row
        await conn.execute("PRAGMA journal_mode=WAL")
        yield conn
