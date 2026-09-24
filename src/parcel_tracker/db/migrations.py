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
        tracking_number TEXT NOT NULL,
        name TEXT,
        carrier_code TEXT,
        carrier_name TEXT,
        all_carriers TEXT,
        status TEXT DEFAULT 'NotFound',
        last_event TEXT,
        last_event_time TEXT,
        user_id INTEGER NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        delivered_at TIMESTAMP,
        is_active INTEGER DEFAULT 1,
        last_check_at TIMESTAMP,
        UNIQUE (user_id, tracking_number)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS tracking_history (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        tracking_number TEXT NOT NULL,
        user_id INTEGER,
        event_time TEXT,
        event_description TEXT,
        location TEXT,
        carrier TEXT,
        notified INTEGER NOT NULL DEFAULT 0,
        recorded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (user_id, tracking_number) REFERENCES parcels(user_id, tracking_number)
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
        await _add_tracking_history_notified(conn)
        await _migrate_to_per_user_uniqueness(conn)
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
        await conn.execute("ALTER TABLE parcels ADD COLUMN delivery_disputed INTEGER DEFAULT 0")


async def _add_allowed_users_language(conn: aiosqlite.Connection) -> None:
    """Idempotent ALTER: add allowed_users.language if missing.

    For new DBs the column is already in CREATE TABLE; this is the upgrade path
    for existing DBs missing the column.
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
    for existing DBs missing the column.
    """
    cursor = await conn.execute("PRAGMA table_info(parcels)")
    rows = await cursor.fetchall()
    columns = {row[1] for row in rows}  # row[1] is column name
    if "last_check_at" not in columns:
        await conn.execute("ALTER TABLE parcels ADD COLUMN last_check_at TIMESTAMP")


async def _add_tracking_history_notified(conn: aiosqlite.Connection) -> None:
    """Idempotent ALTER: add tracking_history.notified for the lost-notification retry.

    New DBs already have the column (DEFAULT 0) from CREATE TABLE. On a legacy DB the
    column is absent; existing rows are marked notified=1 so the first post-upgrade
    cycle does not re-notify the entire backlog. New events are inserted with the
    DEFAULT 0 and flipped to 1 only after a successful (or preference-suppressed) send.
    """
    cursor = await conn.execute("PRAGMA table_info(tracking_history)")
    columns = {row[1] for row in await cursor.fetchall()}
    if "notified" not in columns:
        await conn.execute(
            "ALTER TABLE tracking_history ADD COLUMN notified INTEGER NOT NULL DEFAULT 0"
        )
        await conn.execute("UPDATE tracking_history SET notified = 1")
    await conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_history_notified "
        "ON tracking_history(tracking_number, notified)"
    )


async def _migrate_to_per_user_uniqueness(conn: aiosqlite.Connection) -> None:
    """Migrate to per-user parcel uniqueness + user-scoped tracking history.

    Idempotent, gated on ``tracking_history.user_id`` (absent == a legacy DB from
    before this migration; present == fresh DB built from the new DDL, or already
    migrated). Adds and backfills
    ``tracking_history.user_id`` from the (still globally-unique) parcel owner, then
    recreates ``parcels`` with ``UNIQUE(user_id, tracking_number)`` — dropping the dead
    ``events_json``/``origin``/``destination`` columns in the same rebuild.
    """
    cursor = await conn.execute("PRAGMA table_info(tracking_history)")
    already_migrated = "user_id" in {row[1] for row in await cursor.fetchall()}

    if not already_migrated:
        await _legacy_recreate_for_per_user(conn)

    # Always (fresh + legacy): the user-scoped history index. Created here, after the
    # legacy path has added user_id, because it cannot exist before that column does.
    await conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_history_user_tracking "
        "ON tracking_history(user_id, tracking_number)"
    )


async def _legacy_recreate_for_per_user(conn: aiosqlite.Connection) -> None:
    """Legacy upgrade: add+backfill tracking_history.user_id and recreate parcels."""
    # Backfill while tracking_number is still globally unique (one owner per code).
    await conn.execute("ALTER TABLE tracking_history ADD COLUMN user_id INTEGER")
    await conn.execute(
        "UPDATE tracking_history SET user_id = ("
        "  SELECT p.user_id FROM parcels p "
        "  WHERE p.tracking_number = tracking_history.tracking_number"
        ")"
    )

    # Recreate parcels with the composite uniqueness (SQLite cannot ALTER a constraint).
    await conn.execute(
        """
        CREATE TABLE parcels_p1e (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            tracking_number TEXT NOT NULL,
            name TEXT,
            carrier_code TEXT,
            carrier_name TEXT,
            all_carriers TEXT,
            status TEXT DEFAULT 'NotFound',
            last_event TEXT,
            last_event_time TEXT,
            last_location TEXT,
            transport_mode TEXT,
            delivery_disputed INTEGER DEFAULT 0,
            user_id INTEGER NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            delivered_at TIMESTAMP,
            is_active INTEGER DEFAULT 1,
            last_check_at TIMESTAMP,
            UNIQUE (user_id, tracking_number)
        )
        """
    )
    await conn.execute(
        """
        INSERT INTO parcels_p1e (
            id, tracking_number, name, carrier_code, carrier_name, all_carriers, status,
            last_event, last_event_time, last_location, transport_mode, delivery_disputed,
            user_id, created_at, updated_at, delivered_at, is_active, last_check_at
        )
        SELECT
            id, tracking_number, name, carrier_code, carrier_name, all_carriers, status,
            last_event, last_event_time, last_location, transport_mode, delivery_disputed,
            user_id, created_at, updated_at, delivered_at, is_active, last_check_at
        FROM parcels
        """
    )
    await conn.execute("DROP TABLE parcels")
    await conn.execute("ALTER TABLE parcels_p1e RENAME TO parcels")
    # The parcels recreate dropped its index; restore it (the history index is created
    # unconditionally by the caller for both fresh and legacy paths).
    await conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_parcels_active ON parcels(is_active, user_id)"
    )


# Wait this long for a held write lock before raising SQLITE_BUSY. aiosqlite's
# default connect timeout already yields ~5s; set it explicitly so the guarantee
# does not silently depend on a library default.
_BUSY_TIMEOUT_MS = 5000


@asynccontextmanager
async def get_connection(db_path: str) -> AsyncIterator[aiosqlite.Connection]:
    """Yield an aiosqlite connection with row_factory set to aiosqlite.Row."""
    async with aiosqlite.connect(db_path) as conn:
        conn.row_factory = aiosqlite.Row
        await conn.execute("PRAGMA journal_mode=WAL")
        await conn.execute(f"PRAGMA busy_timeout={_BUSY_TIMEOUT_MS}")
        yield conn
