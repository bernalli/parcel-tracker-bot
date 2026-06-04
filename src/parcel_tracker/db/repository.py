"""Async repositories for parcels, users, and tracking history."""

from __future__ import annotations

import json
from datetime import UTC, datetime

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
                    "INSERT INTO allowed_users (user_id, username, added_by) VALUES (?, ?, ?)",
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

    async def get_language(self, user_id: int) -> str:
        async with get_connection(self._db_path) as conn:
            cursor = await conn.execute(
                "SELECT language FROM allowed_users WHERE user_id = ?",
                (user_id,),
            )
            row = await cursor.fetchone()
        return row["language"] if row else "en"

    async def set_language(self, user_id: int, language: str) -> None:
        async with get_connection(self._db_path) as conn:
            await conn.execute(
                "UPDATE allowed_users SET language = ? WHERE user_id = ?",
                (language, user_id),
            )
            await conn.commit()


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

    async def set_last_check_at(self, tracking_number: str, when: datetime) -> None:
        """Persist the last check timestamp for a parcel (UTC ISO 8601)."""
        async with get_connection(self._db_path) as conn:
            await conn.execute(
                "UPDATE parcels SET last_check_at = ? WHERE tracking_number = ?",
                (when.isoformat(), tracking_number),
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

    async def add_events_dedup(
        self, tracking_number: str, events: list[TrackingEvent]
    ) -> list[TrackingEvent]:
        """Persist events not already in tracking_history. Dedup key = (time, description).

        Returns the newly-inserted events in input order.
        """
        async with get_connection(self._db_path) as conn:
            cursor = await conn.execute(
                "SELECT event_time, event_description FROM tracking_history "
                "WHERE tracking_number = ?",
                (tracking_number,),
            )
            seen = {
                (row["event_time"] or "", row["event_description"] or "")
                for row in await cursor.fetchall()
            }
            new_events: list[TrackingEvent] = []
            for ev in events:
                key = (ev.time or "", ev.description or "")
                if key in seen:
                    continue
                seen.add(key)
                await conn.execute(
                    """
                    INSERT INTO tracking_history
                      (tracking_number, event_time, event_description, location, carrier)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (tracking_number, ev.time, ev.description, ev.location, ev.carrier),
                )
                new_events.append(ev)
            await conn.commit()
        return new_events

    async def update_latest(
        self,
        tracking_number: str,
        last_event: str | None,
        last_event_time: str | None,
        last_location: str | None,
    ) -> None:
        """Update the denormalised latest-event fields on the parcel row."""
        async with get_connection(self._db_path) as conn:
            await conn.execute(
                "UPDATE parcels SET last_event = ?, last_event_time = ?, last_location = ?, "
                "updated_at = CURRENT_TIMESTAMP WHERE tracking_number = ?",
                (last_event, last_event_time, last_location, tracking_number),
            )
            await conn.commit()

    async def set_delivered(self, tracking_number: str, when: datetime) -> None:
        """Mark a parcel Delivered and stamp delivered_at (kept active until confirmed)."""
        async with get_connection(self._db_path) as conn:
            await conn.execute(
                "UPDATE parcels SET status = ?, delivered_at = ?, updated_at = CURRENT_TIMESTAMP "
                "WHERE tracking_number = ?",
                (ShipmentStatus.DELIVERED.value, when.isoformat(), tracking_number),
            )
            await conn.commit()

    async def deactivate(self, tracking_number: str) -> None:
        """Set is_active = 0 to archive a parcel."""
        async with get_connection(self._db_path) as conn:
            await conn.execute(
                "UPDATE parcels SET is_active = 0, updated_at = CURRENT_TIMESTAMP "
                "WHERE tracking_number = ?",
                (tracking_number,),
            )
            await conn.commit()

    async def reactivate(self, tracking_number: str) -> None:
        """Set is_active = 1 to restore an archived parcel."""
        async with get_connection(self._db_path) as conn:
            await conn.execute(
                "UPDATE parcels SET is_active = 1, updated_at = CURRENT_TIMESTAMP "
                "WHERE tracking_number = ?",
                (tracking_number,),
            )
            await conn.commit()

    async def set_disputed(self, tracking_number: str, disputed: bool) -> None:
        """Toggle the delivery_disputed flag on a parcel."""
        async with get_connection(self._db_path) as conn:
            await conn.execute(
                "UPDATE parcels SET delivery_disputed = ?, updated_at = CURRENT_TIMESTAMP "
                "WHERE tracking_number = ?",
                (1 if disputed else 0, tracking_number),
            )
            await conn.commit()

    async def list_archived_for_user(self, *, user_id: int) -> list[Parcel]:
        """Return inactive parcels that were delivered, most recent first."""
        async with get_connection(self._db_path) as conn:
            cursor = await conn.execute(
                "SELECT * FROM parcels WHERE user_id = ? AND is_active = 0 "
                "AND delivered_at IS NOT NULL ORDER BY delivered_at DESC",
                (user_id,),
            )
            rows = await cursor.fetchall()
        return [_row_to_parcel(row) for row in rows]


def _parse_ts(raw: str | None) -> datetime | None:
    if not raw:
        return None
    cleaned = raw.replace("T", " ").split("+")[0].split("Z")[0].strip()
    for fmt in ("%Y-%m-%d %H:%M:%S.%f", "%Y-%m-%d %H:%M:%S"):
        try:
            dt = datetime.strptime(cleaned, fmt)  # noqa: DTZ007
        except ValueError:
            continue
        return dt.replace(tzinfo=UTC)
    return None


def _row_to_parcel(row: aiosqlite.Row) -> Parcel:
    raw_all = row["all_carriers"]
    all_carriers: list[str] = json.loads(raw_all) if raw_all else []
    keys = row.keys()
    last_check_at = _parse_ts(row["last_check_at"]) if "last_check_at" in keys else None
    delivered_at = _parse_ts(row["delivered_at"]) if "delivered_at" in keys else None
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
        last_location=row["last_location"] if "last_location" in keys else None,
        transport_mode=row["transport_mode"] if "transport_mode" in keys else None,
        delivery_disputed=bool(row["delivery_disputed"]) if "delivery_disputed" in keys else False,
        delivered_at=delivered_at,
        last_check_at=last_check_at,
        is_active=bool(row["is_active"]),
    )
