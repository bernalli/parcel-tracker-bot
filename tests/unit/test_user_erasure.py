from __future__ import annotations

from pathlib import Path

from parcel_tracker.db.migrations import get_connection, init_schema
from parcel_tracker.db.models import Parcel, TrackingEvent
from parcel_tracker.db.notification_repository import NotificationRepository
from parcel_tracker.db.repository import ParcelRepository, UserRepository

VICTIM, OTHER = 2002, 3003


async def _counts(db: str, user_id: int) -> dict[str, int]:
    out = {}
    async with get_connection(db) as conn:
        for t in (
            "parcels",
            "tracking_history",
            "user_notification_prefs",
            "notification_cooldown_log",
            "allowed_users",
        ):
            cur = await conn.execute(f"SELECT COUNT(*) FROM {t} WHERE user_id = ?", (user_id,))  # noqa: S608
            out[t] = (await cur.fetchone())[0]
    return out


async def test_remove_user_erases_all_personal_data(tmp_path: Path) -> None:
    db = str(tmp_path / "bot.db")
    await init_schema(db)
    users, repo, prefs = UserRepository(db), ParcelRepository(db), NotificationRepository(db)
    for uid in (VICTIM, OTHER):
        await users.add_user(user_id=uid, added_by=1)
        await repo.create(Parcel(tracking_number="RR123456789DE", user_id=uid, name="Home"))
        await repo.add_events_dedup(
            "RR123456789DE",
            [TrackingEvent(time="t", description="d", location="Via X 1")],
            user_id=uid,
        )
        await prefs.set_pref(user_id=uid, status_value="Delivered", enabled=False)
        await prefs.upsert_cooldown(uid, "RR123456789DE", "Delivered")

    assert await users.remove_user(VICTIM) is True
    assert set((await _counts(db, VICTIM)).values()) == {0}
    assert set((await _counts(db, OTHER)).values()) == {1}
