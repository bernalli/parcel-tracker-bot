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


# Tables holding per-user personal data, children before parents. Web sessions,
# login links and API tokens are included so /forgetme and revocation also end
# every dashboard and API session.
_USER_DATA_TABLES: tuple[str, ...] = (
    "tracking_history",
    "notification_cooldown_log",
    "user_notification_prefs",
    "user_language",
    "user_settings",
    "web_login_tokens",
    "web_sessions",
    "api_tokens",
    "parcels",
)

# Seller fields editable through update_details(); the keys are column names.
DETAIL_FIELDS: tuple[str, ...] = (
    "name",
    "order_ref",
    "recipient",
    "destination",
    "notes",
    "tags",
)


def sql_ts(when: datetime) -> str:
    """Format a datetime the way SQLite's CURRENT_TIMESTAMP does (UTC, no offset).

    Keeping one textual format means SQL-side comparisons such as
    ``updated_at < datetime('now', '-30 days')`` stay correct for values the
    application writes itself.
    """
    if when.tzinfo is not None:
        when = when.astimezone(UTC)
    return when.strftime("%Y-%m-%d %H:%M:%S")


async def _delete_user_rows(conn: aiosqlite.Connection, user_id: int) -> None:
    for table in _USER_DATA_TABLES:
        await conn.execute(
            f"DELETE FROM {table} WHERE user_id = ?",  # noqa: S608  # nosec B608 — fixed table names
            (user_id,),
        )


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

    async def erase_user_data(self, user_id: int) -> None:
        """Delete everything stored about a user, keeping their authorisation as is.

        Used by /forgetme: parcels, tracking history, notification preferences,
        cooldown rows (and any other per-user table) go, in one transaction.
        """
        async with get_connection(self._db_path) as conn:
            await _delete_user_rows(conn, user_id)
            await conn.commit()

    async def remove_user(self, user_id: int) -> bool:
        """Revoke a user and erase everything stored about them, in one transaction.

        Returns True if the user was on the allow-list. Nothing is erased for an ID
        that is not on it: such a user may be authorised another way (owner,
        ADMIN_USER_IDS, ALLOWED_USER_IDS) and keeps using the bot.
        """
        async with get_connection(self._db_path) as conn:
            cursor = await conn.execute("DELETE FROM allowed_users WHERE user_id = ?", (user_id,))
            if not cursor.rowcount:
                return False
            await _delete_user_rows(conn, user_id)
            await conn.commit()
            return True

    async def get_allowed_user_ids(self) -> list[int]:
        async with get_connection(self._db_path) as conn:
            cursor = await conn.execute("SELECT user_id FROM allowed_users")
            rows = await cursor.fetchall()
        return [row["user_id"] for row in rows]

    async def get_language(self, user_id: int, default: str = "en") -> str:
        """The user's chosen UI language, or ``default`` if they never chose one."""
        async with get_connection(self._db_path) as conn:
            cursor = await conn.execute(
                "SELECT language FROM user_language WHERE user_id = ?",
                (user_id,),
            )
            row = await cursor.fetchone()
        return str(row["language"]) if row else default

    async def set_language(self, user_id: int, language: str) -> None:
        """Persist a language choice for any user (owner and env-allowed users included)."""
        async with get_connection(self._db_path) as conn:
            await conn.execute(
                "INSERT INTO user_language (user_id, language) VALUES (?, ?) "
                "ON CONFLICT(user_id) DO UPDATE SET language = excluded.language",
                (user_id, language),
            )
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
        """Insert a parcel and return it as stored (with its id).

        Returns None if the user already tracks this code. A removed or archived
        row for the same code is reactivated instead, keeping its history; the
        seller fields given here replace the stored ones only where they are set.
        """
        async with get_connection(self._db_path) as conn:
            try:
                await conn.execute(
                    """
                    INSERT INTO parcels (
                        tracking_number, name, carrier_code, carrier_name,
                        all_carriers, status, user_id, is_active,
                        order_ref, recipient, destination, notes, tags, last_change_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
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
                        parcel.order_ref,
                        parcel.recipient,
                        parcel.destination,
                        parcel.notes,
                        _dump_tags(parcel.tags),
                    ),
                )
                await conn.commit()
            except aiosqlite.IntegrityError:
                # A removed/archived row for the same code blocks the insert:
                # re-adding it reactivates that row instead of reporting a duplicate.
                cursor = await conn.execute(
                    "UPDATE parcels SET is_active = 1, name = COALESCE(?, name), "
                    "order_ref = COALESCE(?, order_ref), recipient = COALESCE(?, recipient), "
                    "destination = COALESCE(?, destination), notes = COALESCE(?, notes), "
                    "tags = COALESCE(?, tags), "
                    "delivered_at = NULL, delivery_disputed = 0, stall_alerted_at = NULL, "
                    # A terminal status has a zero polling interval: keeping it would
                    # mean the re-added parcel is never fetched again.
                    "status = CASE WHEN status IN ('Delivered', 'Expired') "
                    "THEN 'NotFound' ELSE status END, "
                    "last_event = CASE WHEN status IN ('Delivered', 'Expired') "
                    "THEN NULL ELSE last_event END, "
                    "last_event_time = CASE WHEN status IN ('Delivered', 'Expired') "
                    "THEN NULL ELSE last_event_time END, "
                    "last_check_at = NULL, "
                    "last_change_at = CURRENT_TIMESTAMP, updated_at = CURRENT_TIMESTAMP "
                    "WHERE user_id = ? AND tracking_number = ? AND is_active = 0",
                    (
                        parcel.name,
                        parcel.order_ref,
                        parcel.recipient,
                        parcel.destination,
                        parcel.notes,
                        _dump_tags(parcel.tags) if parcel.tags else None,
                        parcel.user_id,
                        parcel.tracking_number,
                    ),
                )
                await conn.commit()
                if not cursor.rowcount:
                    return None
        return await self.get_for_user(parcel.tracking_number, user_id=parcel.user_id) or parcel

    async def get_by_tracking_number(self, tracking_number: str) -> Parcel | None:
        """Look up a parcel by code WITHOUT owner scoping — test/maintenance only.

        Parcels are unique per (user_id, tracking_number) rather than globally,
        so a code can belong to several users; this returns an arbitrary match.
        Production code must use
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
        """Newest-first event history, ordered by the carrier's event time.

        Insertion order is not chronological (carriers back-fill older scans and
        list events oldest- or newest-first), so rows are sorted by parsed event
        time, with the insertion id as tie-break and for unparseable times.
        """
        from parcel_tracker.maps.route import parse_event_dt  # noqa: PLC0415

        async with get_connection(self._db_path) as conn:
            cursor = await conn.execute(
                "SELECT id, event_time, event_description, location, carrier "
                "FROM tracking_history WHERE tracking_number = ? AND (user_id = ? OR ? IS NULL)",
                (tracking_number, *_owner_params(user_id)),
            )
            rows = await cursor.fetchall()
        ordered = sorted(
            rows,
            key=lambda r: (parse_event_dt(r["event_time"]) or datetime.min, r["id"]),
            reverse=True,
        )
        return [
            TrackingEvent(
                time=row["event_time"] or "",
                description=row["event_description"] or "",
                location=row["location"],
                carrier=row["carrier"],
            )
            for row in ordered[: max(0, limit)]
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

    async def purge_inactive_older_than(self, *, days: int) -> int:
        """Delete removed/archived parcels untouched for ``days`` days, with their
        tracking history and cooldown rows. Returns the number of parcels deleted;
        ``days <= 0`` disables the purge."""
        if days <= 0:
            return 0
        cutoff = f"-{int(days)} days"
        stale = (
            "SELECT user_id, tracking_number FROM parcels "
            "WHERE is_active = 0 AND updated_at < datetime('now', ?)"
        )
        async with get_connection(self._db_path) as conn:
            for table in ("tracking_history", "notification_cooldown_log"):
                await conn.execute(
                    f"DELETE FROM {table} WHERE (user_id, tracking_number) IN ({stale})",  # noqa: S608  # nosec B608 — fixed table names
                    (cutoff,),
                )
            cursor = await conn.execute(
                "DELETE FROM parcels WHERE is_active = 0 AND updated_at < datetime('now', ?)",
                (cutoff,),
            )
            await conn.commit()
            return int(cursor.rowcount or 0)

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

        Scopes directly on ``tracking_history.user_id``: joining on
        ``tracking_number`` alone would over-count when two users track the same code.
        """
        async with get_connection(self._db_path) as conn:
            cursor = await conn.execute(
                "SELECT COUNT(*) AS n FROM tracking_history WHERE user_id = ?",
                (user_id,),
            )
            row = await cursor.fetchone()
        return int(row["n"]) if row else 0

    # --- seller features -------------------------------------------------------

    async def get_by_id_for_user(self, parcel_id: int, *, user_id: int) -> Parcel | None:
        """Fetch a parcel by primary key, only if it belongs to the given user."""
        async with get_connection(self._db_path) as conn:
            cursor = await conn.execute(
                "SELECT * FROM parcels WHERE id = ? AND user_id = ?",
                (parcel_id, user_id),
            )
            row = await cursor.fetchone()
        return _row_to_parcel(row) if row else None

    async def list_all_for_user(self, *, user_id: int) -> list[Parcel]:
        """Every parcel of a user (active, removed and archived), newest first."""
        async with get_connection(self._db_path) as conn:
            cursor = await conn.execute(
                "SELECT * FROM parcels WHERE user_id = ? ORDER BY created_at DESC, id DESC",
                (user_id,),
            )
            rows = await cursor.fetchall()
        return [_row_to_parcel(row) for row in rows]

    async def update_details(
        self, tracking_number: str, *, user_id: int, **fields: str | list[str] | None
    ) -> bool:
        """Update seller fields (see DETAIL_FIELDS); None clears a field.

        Returns True if the parcel exists for this user. Unknown keys raise
        ValueError so a typo can never reach the SQL.
        """
        unknown = set(fields) - set(DETAIL_FIELDS)
        if unknown:
            raise ValueError(f"not editable: {sorted(unknown)}")
        if not fields:
            return await self.get_for_user(tracking_number, user_id=user_id) is not None
        assignments: list[str] = []
        values: list[object] = []
        for key in DETAIL_FIELDS:
            if key not in fields:
                continue
            value = fields[key]
            assignments.append(f"{key} = ?")
            if key == "tags":
                values.append(_dump_tags(value) if isinstance(value, list) else None)
            else:
                values.append(value)
        async with get_connection(self._db_path) as conn:
            cursor = await conn.execute(
                # Column names come from the DETAIL_FIELDS whitelist above.
                f"UPDATE parcels SET {', '.join(assignments)}, updated_at = CURRENT_TIMESTAMP "  # noqa: S608  # nosec B608
                "WHERE tracking_number = ? AND user_id = ?",
                (*values, tracking_number, user_id),
            )
            await conn.commit()
            return bool(cursor.rowcount)

    async def set_share_token(
        self, tracking_number: str, *, user_id: int, token: str | None
    ) -> bool:
        """Set (or clear, with None) the public tracking-page token."""
        async with get_connection(self._db_path) as conn:
            cursor = await conn.execute(
                "UPDATE parcels SET share_token = ? WHERE tracking_number = ? AND user_id = ?",
                (token, tracking_number, user_id),
            )
            await conn.commit()
            return bool(cursor.rowcount)

    async def get_by_share_token(self, token: str) -> Parcel | None:
        """Resolve a public tracking-page token to its parcel (any owner)."""
        if not token:
            return None
        async with get_connection(self._db_path) as conn:
            cursor = await conn.execute("SELECT * FROM parcels WHERE share_token = ?", (token,))
            row = await cursor.fetchone()
        return _row_to_parcel(row) if row else None

    async def touch_change(self, tracking_number: str, when: datetime, *, user_id: int) -> None:
        """Record that the carrier reported something new (resets the stall clock)."""
        async with get_connection(self._db_path) as conn:
            await conn.execute(
                "UPDATE parcels SET last_change_at = ? WHERE tracking_number = ? AND user_id = ?",
                (sql_ts(when), tracking_number, user_id),
            )
            await conn.commit()

    async def mark_stall_alerted(
        self, tracking_number: str, when: datetime, *, user_id: int
    ) -> None:
        """Remember that the stalled-shipment alert went out for the current stall."""
        async with get_connection(self._db_path) as conn:
            await conn.execute(
                "UPDATE parcels SET stall_alerted_at = ? WHERE tracking_number = ? AND user_id = ?",
                (sql_ts(when), tracking_number, user_id),
            )
            await conn.commit()

    async def delete_for_user(self, tracking_number: str, *, user_id: int) -> bool:
        """Delete a parcel and its tracking history for good (not just archive it)."""
        async with get_connection(self._db_path) as conn:
            for table in ("tracking_history", "notification_cooldown_log"):
                await conn.execute(
                    f"DELETE FROM {table} WHERE tracking_number = ? AND user_id = ?",  # noqa: S608  # nosec B608 — fixed table names
                    (tracking_number, user_id),
                )
            cursor = await conn.execute(
                "DELETE FROM parcels WHERE tracking_number = ? AND user_id = ?",
                (tracking_number, user_id),
            )
            await conn.commit()
            return bool(cursor.rowcount)


def _dump_tags(tags: list[str] | None) -> str | None:
    return json.dumps(tags, ensure_ascii=False) if tags else None


def _load_tags(raw: str | None) -> list[str]:
    if not raw:
        return []
    try:
        value = json.loads(raw)
    except ValueError:
        return []
    return [str(t) for t in value] if isinstance(value, list) else []


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
    keys = set(row.keys())

    def col(name: str) -> object:
        return row[name] if name in keys else None

    def text(name: str) -> str | None:
        value = col(name)
        return str(value) if value is not None else None

    def ts(name: str) -> datetime | None:
        value = col(name)
        return _parse_ts(str(value)) if value is not None else None

    raw_all = row["all_carriers"]
    all_carriers: list[str] = json.loads(raw_all) if raw_all else []
    raw_id = col("id")
    return Parcel(
        tracking_number=row["tracking_number"],
        user_id=row["user_id"],
        name=row["name"],
        id=int(str(raw_id)) if raw_id is not None else None,
        order_ref=text("order_ref"),
        recipient=text("recipient"),
        destination=text("destination"),
        notes=text("notes"),
        tags=_load_tags(text("tags")),
        share_token=text("share_token"),
        last_change_at=ts("last_change_at"),
        stall_alerted_at=ts("stall_alerted_at"),
        carrier_code=row["carrier_code"],
        carrier_name=row["carrier_name"],
        all_carriers=all_carriers,
        status=ShipmentStatus.from_str(row["status"]),
        last_event=row["last_event"],
        last_event_time=row["last_event_time"],
        last_location=text("last_location"),
        transport_mode=text("transport_mode"),
        delivery_disputed=bool(col("delivery_disputed")),
        created_at=ts("created_at"),
        updated_at=ts("updated_at"),
        delivered_at=ts("delivered_at"),
        last_check_at=ts("last_check_at"),
        is_active=bool(row["is_active"]),
    )
