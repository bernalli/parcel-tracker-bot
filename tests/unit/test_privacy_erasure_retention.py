"""Self-service erasure (/forgetme) and automatic retention of inactive parcels."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from parcel_tracker.db.migrations import get_connection, init_schema
from parcel_tracker.db.models import Parcel, TrackingEvent
from parcel_tracker.db.notification_repository import NotificationRepository
from parcel_tracker.db.repository import ParcelRepository, UserRepository

ALICE, BOB = 2, 3
TABLES = ("parcels", "tracking_history", "user_notification_prefs", "notification_cooldown_log")


@pytest.fixture
async def db(tmp_path: Path) -> str:
    path = str(tmp_path / "bot.db")
    await init_schema(path)
    return path


async def _seed(db: str, uid: int, code: str = "RR123456789DE") -> None:
    repo, prefs = ParcelRepository(db), NotificationRepository(db)
    await repo.create(Parcel(tracking_number=code, user_id=uid, name="Home"))
    await repo.add_events_dedup(
        code, [TrackingEvent(time="t", description="d", location="Via X 1")], user_id=uid
    )
    await prefs.set_pref(user_id=uid, status_value="Delivered", enabled=False)
    await prefs.upsert_cooldown(uid, code, "Delivered")


async def _count(db: str, table: str, uid: int) -> int:
    async with get_connection(db) as conn:
        cur = await conn.execute(f"SELECT COUNT(*) FROM {table} WHERE user_id = ?", (uid,))  # noqa: S608
        return int((await cur.fetchone())[0])


async def test_erase_user_data_keeps_authorisation(db: str) -> None:
    users = UserRepository(db)
    await users.add_user(user_id=ALICE, added_by=1)
    await _seed(db, ALICE)
    await _seed(db, BOB)
    await users.erase_user_data(ALICE)
    assert [await _count(db, t, ALICE) for t in TABLES] == [0, 0, 0, 0]
    assert [await _count(db, t, BOB) for t in TABLES] == [1, 1, 1, 1]
    assert ALICE in await users.get_allowed_user_ids()


async def test_forgetme_asks_for_confirmation_then_erases(db: str) -> None:
    from parcel_tracker.bot import callbacks
    from parcel_tracker.bot.privacy_commands import cmd_forgetme

    users = UserRepository(db)
    await _seed(db, ALICE)
    reply = AsyncMock()
    msg = SimpleNamespace(reply_text=reply)
    upd = SimpleNamespace(
        effective_user=SimpleNamespace(id=ALICE), effective_message=msg, message=msg
    )
    ctx = SimpleNamespace(args=[], user_data={}, bot_data={"user_repo": users})
    await cmd_forgetme(upd, ctx)  # type: ignore[arg-type]
    assert await _count(db, "parcels", ALICE) == 1  # nothing deleted before confirming
    markup = reply.await_args.kwargs["reply_markup"]
    datas = [b.callback_data for row in markup.inline_keyboard for b in row]
    assert "action:forgetme_do" in datas

    query = SimpleNamespace(
        data="action:forgetme_do",
        answer=AsyncMock(),
        edit_message_text=AsyncMock(),
        from_user=SimpleNamespace(id=ALICE),
    )
    cb = SimpleNamespace(callback_query=query, effective_user=SimpleNamespace(id=ALICE))
    await callbacks.handle_callback(cb, ctx)  # type: ignore[arg-type]
    assert [await _count(db, t, ALICE) for t in TABLES] == [0, 0, 0, 0]


async def test_retention_purges_old_inactive_parcels_only(db: str) -> None:
    repo = ParcelRepository(db)
    await _seed(db, ALICE, "RR000000001DE")  # old and removed -> purged
    await _seed(db, ALICE, "RR000000002DE")  # recent and removed -> kept
    await _seed(db, ALICE, "RR000000003DE")  # old but active -> kept
    await repo.deactivate("RR000000001DE", user_id=ALICE)
    await repo.deactivate("RR000000002DE", user_id=ALICE)
    old = (datetime.now(UTC) - timedelta(days=400)).strftime("%Y-%m-%d %H:%M:%S")
    async with get_connection(db) as conn:
        await conn.execute(
            "UPDATE parcels SET updated_at = ? WHERE tracking_number IN (?, ?)",
            (old, "RR000000001DE", "RR000000003DE"),
        )
        await conn.commit()

    purged = await repo.purge_inactive_older_than(days=180)

    assert purged == 1
    assert await repo.get_for_user("RR000000001DE", user_id=ALICE) is None
    assert await repo.get_for_user("RR000000002DE", user_id=ALICE) is not None
    assert await repo.get_for_user("RR000000003DE", user_id=ALICE) is not None
    async with get_connection(db) as conn:
        cur = await conn.execute(
            "SELECT COUNT(*) FROM tracking_history WHERE tracking_number = ?", ("RR000000001DE",)
        )
        assert (await cur.fetchone())[0] == 0
        cur = await conn.execute(
            "SELECT COUNT(*) FROM notification_cooldown_log WHERE tracking_number = ?",
            ("RR000000001DE",),
        )
        assert (await cur.fetchone())[0] == 0


async def test_retention_disabled_with_zero(db: str) -> None:
    repo = ParcelRepository(db)
    await _seed(db, ALICE)
    await repo.deactivate("RR123456789DE", user_id=ALICE)
    assert await repo.purge_inactive_older_than(days=0) == 0
    assert await _count(db, "parcels", ALICE) == 1


def test_retention_days_config(monkeypatch: pytest.MonkeyPatch) -> None:
    from parcel_tracker.config import Config

    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "x")
    monkeypatch.setenv("OWNER_ID", "1")
    monkeypatch.delenv("DATA_RETENTION_DAYS", raising=False)
    assert Config.from_env(load_dotenv_file=False).data_retention_days == 180
    monkeypatch.setenv("DATA_RETENTION_DAYS", "0")
    assert Config.from_env(load_dotenv_file=False).data_retention_days == 0


async def test_scheduler_tick_applies_retention(db: str) -> None:
    from parcel_tracker.core.scheduler import _apply_retention

    repo = ParcelRepository(db)
    await _seed(db, ALICE)
    await repo.deactivate("RR123456789DE", user_id=ALICE)
    async with get_connection(db) as conn:
        await conn.execute("UPDATE parcels SET updated_at = '2000-01-01 00:00:00'")
        await conn.commit()
    await _apply_retention(repo, 0)
    assert await _count(db, "parcels", ALICE) == 1  # disabled
    await _apply_retention(repo, 30)
    assert await _count(db, "parcels", ALICE) == 0
