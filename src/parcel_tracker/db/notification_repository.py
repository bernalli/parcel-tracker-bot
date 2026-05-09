"""CRUD for user_notification_prefs and notification_cooldown_log tables."""

from __future__ import annotations

from datetime import UTC, datetime

from parcel_tracker.db.migrations import get_connection


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


class NotificationRepository:
    """CRUD on user_notification_prefs + notification_cooldown_log."""

    def __init__(self, db_path: str) -> None:
        self._db_path = db_path

    # --- prefs ---

    async def get_pref(self, user_id: int, status_value: str) -> bool | None:
        async with get_connection(self._db_path) as conn:
            cursor = await conn.execute(
                "SELECT enabled FROM user_notification_prefs "
                "WHERE user_id = ? AND status_value = ?",
                (user_id, status_value),
            )
            row = await cursor.fetchone()
        if row is None:
            return None
        return bool(row["enabled"])

    async def set_pref(self, user_id: int, status_value: str, enabled: bool) -> None:
        async with get_connection(self._db_path) as conn:
            await conn.execute(
                """
                INSERT INTO user_notification_prefs (user_id, status_value, enabled)
                VALUES (?, ?, ?)
                ON CONFLICT(user_id, status_value) DO UPDATE SET enabled = excluded.enabled
                """,
                (user_id, status_value, 1 if enabled else 0),
            )
            await conn.commit()

    async def get_all_prefs(self, user_id: int) -> dict[str, bool]:
        async with get_connection(self._db_path) as conn:
            cursor = await conn.execute(
                "SELECT status_value, enabled FROM user_notification_prefs "
                "WHERE user_id = ? ORDER BY status_value",
                (user_id,),
            )
            rows = await cursor.fetchall()
        return {row["status_value"]: bool(row["enabled"]) for row in rows}

    # --- cooldown log ---

    async def get_last_sent(
        self, user_id: int, tracking_number: str, status_value: str
    ) -> datetime | None:
        async with get_connection(self._db_path) as conn:
            cursor = await conn.execute(
                """
                SELECT sent_at FROM notification_cooldown_log
                WHERE user_id = ? AND tracking_number = ? AND status_value = ?
                """,
                (user_id, tracking_number, status_value),
            )
            row = await cursor.fetchone()
        if row is None:
            return None
        return _parse_ts(row["sent_at"])

    async def upsert_cooldown(self, user_id: int, tracking_number: str, status_value: str) -> None:
        async with get_connection(self._db_path) as conn:
            await conn.execute(
                """
                INSERT INTO notification_cooldown_log
                  (user_id, tracking_number, status_value, sent_at)
                VALUES (?, ?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(user_id, tracking_number, status_value) DO UPDATE SET
                  sent_at = CURRENT_TIMESTAMP
                """,
                (user_id, tracking_number, status_value),
            )
            await conn.commit()
