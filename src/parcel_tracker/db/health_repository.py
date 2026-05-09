"""Repository for tracker health state (quarantine, success/failure tracking)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from parcel_tracker.db.migrations import get_connection


@dataclass(slots=True)
class HealthState:
    tracker_id: str
    tracking_id: str
    last_success_at: datetime | None
    last_failure_at: datetime | None
    consecutive_failures: int
    consecutive_successes: int
    quarantine_until: datetime | None
    total_checks: int
    total_failures: int


class HealthRepository:
    """CRUD for tracker_health table."""

    def __init__(self, db_path: str) -> None:
        self._db_path = db_path

    async def record_success(self, tracker_id: str, tracking_id: str = "") -> None:
        async with get_connection(self._db_path) as conn:
            await conn.execute(
                """
                INSERT INTO tracker_health
                  (tracker_id, tracking_id, last_success_at, consecutive_successes,
                   consecutive_failures, total_checks)
                VALUES (?, ?, CURRENT_TIMESTAMP, 1, 0, 1)
                ON CONFLICT(tracker_id, tracking_id) DO UPDATE SET
                  last_success_at = CURRENT_TIMESTAMP,
                  consecutive_successes = consecutive_successes + 1,
                  consecutive_failures = 0,
                  quarantine_until = NULL,
                  total_checks = total_checks + 1
                """,
                (tracker_id, tracking_id),
            )
            await conn.commit()

    async def record_failure(self, tracker_id: str, tracking_id: str = "") -> None:
        async with get_connection(self._db_path) as conn:
            await conn.execute(
                """
                INSERT INTO tracker_health
                  (tracker_id, tracking_id, last_failure_at, consecutive_failures,
                   consecutive_successes, total_checks, total_failures)
                VALUES (?, ?, CURRENT_TIMESTAMP, 1, 0, 1, 1)
                ON CONFLICT(tracker_id, tracking_id) DO UPDATE SET
                  last_failure_at = CURRENT_TIMESTAMP,
                  consecutive_failures = consecutive_failures + 1,
                  consecutive_successes = 0,
                  total_checks = total_checks + 1,
                  total_failures = total_failures + 1
                """,
                (tracker_id, tracking_id),
            )
            await conn.commit()

    async def set_quarantine(
        self,
        tracker_id: str,
        tracking_id: str,
        quarantine_until: datetime,
    ) -> None:
        async with get_connection(self._db_path) as conn:
            await conn.execute(
                """
                INSERT INTO tracker_health (tracker_id, tracking_id, quarantine_until)
                VALUES (?, ?, ?)
                ON CONFLICT(tracker_id, tracking_id) DO UPDATE SET
                  quarantine_until = excluded.quarantine_until
                """,
                (tracker_id, tracking_id, quarantine_until.isoformat()),
            )
            await conn.commit()

    async def is_quarantined(self, tracker_id: str, tracking_id: str = "") -> bool:
        async with get_connection(self._db_path) as conn:
            cursor = await conn.execute(
                "SELECT quarantine_until FROM tracker_health "
                "WHERE tracker_id = ? AND tracking_id = ?",
                (tracker_id, tracking_id),
            )
            row = await cursor.fetchone()
        if row is None or row["quarantine_until"] is None:
            return False
        until = _parse_ts(row["quarantine_until"])
        return until is not None and until > datetime.now(UTC)

    async def get_state(self, tracker_id: str, tracking_id: str = "") -> HealthState | None:
        async with get_connection(self._db_path) as conn:
            cursor = await conn.execute(
                "SELECT * FROM tracker_health " "WHERE tracker_id = ? AND tracking_id = ?",
                (tracker_id, tracking_id),
            )
            row = await cursor.fetchone()
        if row is None:
            return None
        return HealthState(
            tracker_id=row["tracker_id"],
            tracking_id=row["tracking_id"],
            last_success_at=_parse_ts(row["last_success_at"]),
            last_failure_at=_parse_ts(row["last_failure_at"]),
            consecutive_failures=row["consecutive_failures"],
            consecutive_successes=row["consecutive_successes"],
            quarantine_until=_parse_ts(row["quarantine_until"]),
            total_checks=row["total_checks"],
            total_failures=row["total_failures"],
        )


def _parse_ts(raw: str | None) -> datetime | None:
    if not raw:
        return None
    # SQLite returns CURRENT_TIMESTAMP as 'YYYY-MM-DD HH:MM:SS'
    cleaned = raw.replace("T", " ").split("+")[0].split("Z")[0].strip()
    try:
        dt = datetime.strptime(cleaned, "%Y-%m-%d %H:%M:%S.%f")  # noqa: DTZ007
    except ValueError:
        try:
            dt = datetime.strptime(cleaned, "%Y-%m-%d %H:%M:%S")  # noqa: DTZ007
        except ValueError:
            return None
    return dt.replace(tzinfo=UTC)
