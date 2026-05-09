"""Async repositories for parcels, users, and tracking history."""

from __future__ import annotations

import json

import aiosqlite

from parcel_tracker.db.migrations import get_connection
from parcel_tracker.db.models import Parcel, ShipmentStatus, TrackingEvent


class UserRepository:
    """CRUD for the allowed_users table."""

    def __init__(self, db_path: str) -> None:
        self._db_path = db_path

    async def add_user(
        self,
        *,
        user_id: int,
        added_by: int,
        username: str | None = None,
    ) -> bool:
        """Add a user to the allowed list. Returns True if added, False if duplicate."""
        async with get_connection(self._db_path) as conn:
            try:
                await conn.execute(
                    "INSERT INTO allowed_users (user_id, username, added_by) " "VALUES (?, ?, ?)",
                    (user_id, username, added_by),
                )
                await conn.commit()
                return True
            except aiosqlite.IntegrityError:
                return False

    async def remove_user(self, user_id: int) -> bool:
        async with get_connection(self._db_path) as conn:
            cursor = await conn.execute("DELETE FROM allowed_users WHERE user_id = ?", (user_id,))
            await conn.commit()
            return bool(cursor.rowcount)

    async def get_allowed_user_ids(self) -> list[int]:
        async with get_connection(self._db_path) as conn:
            cursor = await conn.execute("SELECT user_id FROM allowed_users")
            rows = await cursor.fetchall()
        return [row["user_id"] for row in rows]


class ParcelRepository:
    """CRUD for the parcels and tracking_history tables."""

    def __init__(self, db_path: str) -> None:
        self._db_path = db_path

    async def create(self, parcel: Parcel) -> Parcel:
        async with get_connection(self._db_path) as conn:
            await conn.execute(
                """
                INSERT INTO parcels (
                    tracking_number, name, carrier_code, carrier_name,
                    all_carriers, status, user_id, is_active
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    parcel.tracking_number,
                    parcel.name,
                    parcel.carrier_code,
                    parcel.carrier_name,
                    json.dumps(parcel.all_carriers),
                    parcel.status.value,
                    parcel.user_id,
                    int(parcel.is_active),
                ),
            )
            await conn.commit()
        return parcel

    async def get_by_tracking_number(self, tracking_number: str) -> Parcel | None:
        async with get_connection(self._db_path) as conn:
            cursor = await conn.execute(
                "SELECT * FROM parcels WHERE tracking_number = ?",
                (tracking_number,),
            )
            row = await cursor.fetchone()
        return _row_to_parcel(row) if row else None

    async def list_active_for_user(self, *, user_id: int) -> list[Parcel]:
        async with get_connection(self._db_path) as conn:
            cursor = await conn.execute(
                "SELECT * FROM parcels WHERE user_id = ? AND is_active = 1 "
                "ORDER BY created_at DESC",
                (user_id,),
            )
            rows = await cursor.fetchall()
        return [_row_to_parcel(row) for row in rows]

    async def update_status(self, tracking_number: str, status: ShipmentStatus) -> None:
        async with get_connection(self._db_path) as conn:
            await conn.execute(
                "UPDATE parcels SET status = ?, updated_at = CURRENT_TIMESTAMP "
                "WHERE tracking_number = ?",
                (status.value, tracking_number),
            )
            await conn.commit()

    async def add_event(self, tracking_number: str, event: TrackingEvent) -> None:
        async with get_connection(self._db_path) as conn:
            await conn.execute(
                """
                INSERT INTO tracking_history
                  (tracking_number, event_time, event_description, location, carrier)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    tracking_number,
                    event.time,
                    event.description,
                    event.location,
                    event.carrier,
                ),
            )
            await conn.commit()

    async def get_history(self, tracking_number: str, *, limit: int = 100) -> list[TrackingEvent]:
        async with get_connection(self._db_path) as conn:
            cursor = await conn.execute(
                "SELECT event_time, event_description, location, carrier "
                "FROM tracking_history WHERE tracking_number = ? "
                "ORDER BY recorded_at DESC LIMIT ?",
                (tracking_number, limit),
            )
            rows = await cursor.fetchall()
        return [
            TrackingEvent(
                time=row["event_time"] or "",
                description=row["event_description"] or "",
                location=row["location"],
                carrier=row["carrier"],
            )
            for row in rows
        ]


def _row_to_parcel(row: aiosqlite.Row) -> Parcel:
    raw_all = row["all_carriers"]
    all_carriers: list[str] = json.loads(raw_all) if raw_all else []
    return Parcel(
        tracking_number=row["tracking_number"],
        user_id=row["user_id"],
        name=row["name"],
        carrier_code=row["carrier_code"],
        carrier_name=row["carrier_name"],
        all_carriers=all_carriers,
        status=ShipmentStatus.from_str(row["status"]),
        last_event=row["last_event"],
        last_event_time=row["last_event_time"],
        is_active=bool(row["is_active"]),
    )
