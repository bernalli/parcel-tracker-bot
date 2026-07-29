"""Async repositories for parcels, users, and tracking history."""

from __future__ import annotations

import json
from datetime import UTC, datetime

import aiosqlite

from parcel_tracker.db.migrations import get_connection
from parcel_tracker.db.models import Parcel, ShipmentStatus, TrackingEvent


def _owner_params(user_id: int | None) -> tuple[int | None, int | None]:
    """Bind params for the static ``AND (user_id = ? OR ? IS NULL)`` owner filter.

    The filter is a constant SQL fragment (no string interpolation) inlined in each
    query. The ``? IS NULL`` arm matches every owner when ``user_id`` is None
    (legacy/test single-user callers); when set it pins the owner. Production callers
    (scheduler + bot) always pass user_id so two users sharing a code stay isolated.
    """
    return (user_id, user_id)


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

    async def create(self, parcel: Parcel) -> Parcel | None:
        """Insert a parcel. Returns the parcel, or None if the tracking_number already exists."""
        async with get_connection(self._db_path) as conn:
            try:
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
            except aiosqlite.IntegrityError:
                return None
        return parcel

    async def get_by_tracking_number(self, tracking_number: str) -> Parcel | None:
        """Look up a parcel by code WITHOUT owner scoping — test/maintenance only.

        Since P1-e (UNIQUE(user_id, tracking_number)) a code can belong to several
        users; this returns an arbitrary match. Production code must use
        :meth:`get_for_user` instead.
        """
        async with get_connection(self._db_path) as conn:
            cursor = await conn.execute(
                "SELECT * FROM parcels WHERE tracking_number = ?",
                (tracking_number,),
            )
            row = await cursor.fetchone()
        return _row_to_parcel(row) if row else None

    async def get_for_user(self, tracking_number: str, *, user_id: int) -> Parcel | None:
        """Fetch a parcel only if it belongs to the given user (ownership-scoped)."""
        async with get_connection(self._db_path) as conn:
            cursor = await conn.execute(
                "SELECT * FROM parcels WHERE tracking_number = ? AND user_id = ?",
                (tracking_number, user_id),
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

    async def list_active_delivered_unstamped(self) -> list[Parcel]:
        """Active parcels marked DELIVERED but missing delivered_at — the pre-lifecycle
        backlog the startup reconciliation heals (stamp + single confirmation)."""
        async with get_connection(self._db_path) as conn:
            cursor = await conn.execute(
                "SELECT * FROM parcels WHERE is_active = 1 AND status = ? "
                "AND delivered_at IS NULL ORDER BY created_at",
                (ShipmentStatus.DELIVERED.value,),
            )
            rows = await cursor.fetchall()
        return [_row_to_parcel(row) for row in rows]

    async def count_active_for_user(self, *, user_id: int) -> int:
        """Number of active (non-archived) parcels owned by the user."""
        async with get_connection(self._db_path) as conn:
            cursor = await conn.execute(
                "SELECT COUNT(*) AS n FROM parcels WHERE user_id = ? AND is_active = 1",
                (user_id,),
            )
            row = await cursor.fetchone()
        return int(row["n"]) if row else 0

    async def update_status(
        self, tracking_number: str, status: ShipmentStatus, *, user_id: int | None = None
    ) -> None:
        async with get_connection(self._db_path) as conn:
            await conn.execute(
                "UPDATE parcels SET status = ?, updated_at = CURRENT_TIMESTAMP "
                "WHERE tracking_number = ? AND (user_id = ? OR ? IS NULL)",
                (status.value, tracking_number, *_owner_params(user_id)),
            )
            await conn.commit()

    async def set_last_check_at(
        self, tracking_number: str, when: datetime, *, user_id: int | None = None
    ) -> None:
        """Persist the last check timestamp for a parcel (UTC ISO 8601)."""
        async with get_connection(self._db_path) as conn:
            await conn.execute(
                "UPDATE parcels SET last_check_at = ? "
                "WHERE tracking_number = ? AND (user_id = ? OR ? IS NULL)",
                (when.isoformat(), tracking_number, *_owner_params(user_id)),
            )
            await conn.commit()

    async def get_history(
        self, tracking_number: str, *, limit: int = 100, user_id: int | None = None
    ) -> list[TrackingEvent]:
        async with get_connection(self._db_path) as conn:
            cursor = await conn.execute(
                "SELECT event_time, event_description, location, carrier "
                "FROM tracking_history WHERE tracking_number = ? AND (user_id = ? OR ? IS NULL) "
                "ORDER BY recorded_at DESC LIMIT ?",
                (tracking_number, *_owner_params(user_id), limit),
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
        self, tracking_number: str, events: list[TrackingEvent], *, user_id: int | None = None
    ) -> list[TrackingEvent]:
        """Persist events not already in tracking_history. Dedup key = (time, description),
        scoped to the owner so two users tracking the same code keep separate histories.

        Returns the newly-inserted events in input order.
        """
        async with get_connection(self._db_path) as conn:
            cursor = await conn.execute(
                "SELECT event_time, event_description FROM tracking_history "
                "WHERE tracking_number = ? AND (user_id = ? OR ? IS NULL)",
                (tracking_number, *_owner_params(user_id)),
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
                      (tracking_number, user_id, event_time, event_description, location, carrier)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (tracking_number, user_id, ev.time, ev.description, ev.location, ev.carrier),
                )
                new_events.append(ev)
            await conn.commit()
        return new_events

    async def get_unnotified(
        self, tracking_number: str, *, user_id: int | None = None
    ) -> list[tuple[int, TrackingEvent]]:
        """Return (row_id, event) for events not yet successfully notified, oldest first.

        Drives the notification retry: an event stays here until a send succeeds (or
        is suppressed by the user's preference), so a transient Telegram failure is
        re-attempted next cycle instead of being lost.
        """
        async with get_connection(self._db_path) as conn:
            cursor = await conn.execute(
                "SELECT id, event_time, event_description, location, carrier "
                "FROM tracking_history WHERE tracking_number = ? AND notified = 0 "
                "AND (user_id = ? OR ? IS NULL) ORDER BY id",
                (tracking_number, *_owner_params(user_id)),
            )
            rows = await cursor.fetchall()
        return [
            (
                row["id"],
                TrackingEvent(
                    time=row["event_time"] or "",
                    description=row["event_description"] or "",
                    location=row["location"],
                    carrier=row["carrier"],
                ),
            )
            for row in rows
        ]

    async def mark_notified(self, event_ids: list[int]) -> None:
        """Flag specific tracking_history rows (by id) as successfully notified."""
        if not event_ids:
            return
        placeholders = ",".join("?" for _ in event_ids)
        async with get_connection(self._db_path) as conn:
            await conn.execute(
                # placeholders is only "?,?,..." built from len(event_ids); the ids
                # themselves are bound as parameters, never interpolated.
                f"UPDATE tracking_history SET notified = 1 WHERE id IN ({placeholders})",  # noqa: S608  # nosec B608
                event_ids,
            )
            await conn.commit()

    async def update_latest(
        self,
        tracking_number: str,
        last_event: str | None,
        last_event_time: str | None,
        last_location: str | None,
        *,
        user_id: int | None = None,
    ) -> None:
        """Update the denormalised latest-event fields on the parcel row."""
        async with get_connection(self._db_path) as conn:
            await conn.execute(
                "UPDATE parcels SET last_event = ?, last_event_time = ?, last_location = ?, "
                "updated_at = CURRENT_TIMESTAMP "
                "WHERE tracking_number = ? AND (user_id = ? OR ? IS NULL)",
                (
                    last_event,
                    last_event_time,
                    last_location,
                    tracking_number,
                    *_owner_params(user_id),
                ),
            )
            await conn.commit()

    async def update_carrier(
        self,
        tracking_number: str,
        carrier_code: str | None,
        carrier_name: str | None,
        *,
        user_id: int | None = None,
    ) -> None:
        """Persist the carrier identity learned during a fetch.

        Carrier is set at creation only; trackers re-identify it on every fetch,
        so this keeps the parcel row in sync (and replaces the "?" placeholder
        shown for parcels added before detection or served by a scraper plugin).
        """
        async with get_connection(self._db_path) as conn:
            await conn.execute(
                "UPDATE parcels SET carrier_code = ?, carrier_name = ?, "
                "updated_at = CURRENT_TIMESTAMP "
                "WHERE tracking_number = ? AND (user_id = ? OR ? IS NULL)",
                (carrier_code, carrier_name, tracking_number, *_owner_params(user_id)),
            )
            await conn.commit()

    async def set_delivered(
        self, tracking_number: str, when: datetime, *, user_id: int | None = None
    ) -> None:
        """Mark a parcel Delivered and stamp delivered_at (kept active until confirmed)."""
        async with get_connection(self._db_path) as conn:
            await conn.execute(
                "UPDATE parcels SET status = ?, delivered_at = ?, updated_at = CURRENT_TIMESTAMP "
                "WHERE tracking_number = ? AND (user_id = ? OR ? IS NULL)",
                (
                    ShipmentStatus.DELIVERED.value,
                    when.isoformat(),
                    tracking_number,
                    *_owner_params(user_id),
                ),
            )
            await conn.commit()

    async def archive_delivered_for_user(self, *, user_id: int) -> int:
        """Deactivate all active Delivered parcels for a user. Returns count archived."""
        async with get_connection(self._db_path) as conn:
            cursor = await conn.execute(
                "UPDATE parcels SET is_active = 0, updated_at = CURRENT_TIMESTAMP "
                "WHERE user_id = ? AND is_active = 1 AND status = ?",
                (user_id, ShipmentStatus.DELIVERED.value),
            )
            await conn.commit()
            return cursor.rowcount

    async def deactivate_all_for_user(self, *, user_id: int) -> int:
        """Deactivate ALL active parcels for a user (archive everything). Returns count."""
        async with get_connection(self._db_path) as conn:
            cursor = await conn.execute(
                "UPDATE parcels SET is_active = 0, updated_at = CURRENT_TIMESTAMP "
                "WHERE user_id = ? AND is_active = 1",
                (user_id,),
            )
            await conn.commit()
            return cursor.rowcount

    async def deactivate(self, tracking_number: str, *, user_id: int | None = None) -> None:
        """Set is_active = 0 to archive a parcel."""
        async with get_connection(self._db_path) as conn:
            await conn.execute(
                "UPDATE parcels SET is_active = 0, updated_at = CURRENT_TIMESTAMP "
                "WHERE tracking_number = ? AND (user_id = ? OR ? IS NULL)",
                (tracking_number, *_owner_params(user_id)),
            )
            await conn.commit()

    async def reactivate(self, tracking_number: str, *, user_id: int | None = None) -> None:
        """Set is_active = 1 to restore an archived parcel."""
        async with get_connection(self._db_path) as conn:
            await conn.execute(
                "UPDATE parcels SET is_active = 1, updated_at = CURRENT_TIMESTAMP "
                "WHERE tracking_number = ? AND (user_id = ? OR ? IS NULL)",
                (tracking_number, *_owner_params(user_id)),
            )
            await conn.commit()

    async def set_disputed(
        self, tracking_number: str, disputed: bool, *, user_id: int | None = None
    ) -> None:
        """Toggle the delivery_disputed flag on a parcel."""
        async with get_connection(self._db_path) as conn:
            await conn.execute(
                "UPDATE parcels SET delivery_disputed = ?, updated_at = CURRENT_TIMESTAMP "
                "WHERE tracking_number = ? AND (user_id = ? OR ? IS NULL)",
                (1 if disputed else 0, tracking_number, *_owner_params(user_id)),
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

    async def rename(self, tracking_number: str, *, user_id: int, name: str) -> bool:
        """Set a parcel's display name, scoped to its owner. Returns True if a row changed."""
        async with get_connection(self._db_path) as conn:
            cursor = await conn.execute(
                "UPDATE parcels SET name = ?, updated_at = CURRENT_TIMESTAMP "
                "WHERE tracking_number = ? AND user_id = ?",
                (name, tracking_number, user_id),
            )
            await conn.commit()
            return bool(cursor.rowcount)

    async def count_events_for_user(self, *, user_id: int) -> int:
        """Count tracking-history rows owned by a user.

        Scopes directly on ``tracking_history.user_id`` (P1-e): joining on
        ``tracking_number`` alone would over-count when two users track the same code.
        """
        async with get_connection(self._db_path) as conn:
            cursor = await conn.execute(
                "SELECT COUNT(*) AS n FROM tracking_history WHERE user_id = ?",
                (user_id,),
            )
            row = await cursor.fetchone()
        return int(row["n"]) if row else 0


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
