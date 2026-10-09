"""Seller columns, detail edits, share tokens and erasure of the new tables."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import aiosqlite
import pytest

from parcel_tracker.db.migrations import init_schema
from parcel_tracker.db.models import Parcel
from parcel_tracker.db.repository import ParcelRepository, UserRepository, sql_ts
from parcel_tracker.db.settings_repository import SettingsRepository
from parcel_tracker.db.web_repository import WebRepository


async def _repo(path) -> ParcelRepository:
    await init_schema(str(path))
    return ParcelRepository(str(path))


async def test_create_returns_stored_parcel_with_seller_fields(tmp_db_path) -> None:
    repo = await _repo(tmp_db_path)
    created = await repo.create(
        Parcel(
            tracking_number="RR123456785IT",
            user_id=1,
            name="Mug",
            order_ref="#1001",
            recipient="Ada",
            destination="Milano, IT",
            notes="fragile",
            tags=["vip", "express"],
        )
    )
    assert created is not None
    assert created.id is not None
    assert created.order_ref == "#1001"
    assert created.recipient == "Ada"
    assert created.destination == "Milano, IT"
    assert created.notes == "fragile"
    assert created.tags == ["vip", "express"]
    assert created.created_at is not None
    assert created.last_change_at is not None
    again = await repo.get_by_id_for_user(created.id, user_id=1)
    assert again == created
    assert await repo.get_by_id_for_user(created.id, user_id=2) is None


async def test_reactivation_keeps_fields_and_resets_stall_clock(tmp_db_path) -> None:
    repo = await _repo(tmp_db_path)
    await repo.create(Parcel(tracking_number="TN100001", user_id=1, order_ref="A1"))
    await repo.mark_stall_alerted("TN100001", datetime(2026, 1, 1, tzinfo=UTC), user_id=1)
    await repo.deactivate("TN100001", user_id=1)
    again = await repo.create(Parcel(tracking_number="TN100001", user_id=1, recipient="Bob"))
    assert again is not None
    assert again.is_active
    assert again.order_ref == "A1"
    assert again.recipient == "Bob"
    assert again.stall_alerted_at is None
    assert await repo.create(Parcel(tracking_number="TN100001", user_id=1)) is None


async def test_update_details_whitelist_and_clear(tmp_db_path) -> None:
    repo = await _repo(tmp_db_path)
    await repo.create(Parcel(tracking_number="TN100002", user_id=1, notes="x", tags=["a"]))
    assert await repo.update_details("TN100002", user_id=1, recipient="Eve", notes=None, tags=[])
    p = await repo.get_for_user("TN100002", user_id=1)
    assert p is not None
    assert (p.recipient, p.notes, p.tags) == ("Eve", None, [])
    assert not await repo.update_details("TN100002", user_id=2, recipient="Mallory")
    with pytest.raises(ValueError, match="not editable"):
        await repo.update_details("TN100002", user_id=1, status="Delivered")


async def test_share_token_roundtrip(tmp_db_path) -> None:
    repo = await _repo(tmp_db_path)
    await repo.create(Parcel(tracking_number="TN100003", user_id=1))
    assert await repo.get_by_share_token("") is None
    assert await repo.set_share_token("TN100003", user_id=1, token="tok123")
    found = await repo.get_by_share_token("tok123")
    assert found is not None
    assert found.tracking_number == "TN100003"
    await repo.set_share_token("TN100003", user_id=1, token=None)
    assert await repo.get_by_share_token("tok123") is None


async def test_touch_change_and_list_all(tmp_db_path) -> None:
    repo = await _repo(tmp_db_path)
    await repo.create(Parcel(tracking_number="TN100004", user_id=1))
    await repo.create(Parcel(tracking_number="TN100005", user_id=1))
    await repo.deactivate("TN100005", user_id=1)
    when = datetime(2026, 3, 1, 8, 30, tzinfo=UTC)
    await repo.touch_change("TN100004", when, user_id=1)
    everything = await repo.list_all_for_user(user_id=1)
    assert {p.tracking_number for p in everything} == {"TN100004", "TN100005"}
    p = await repo.get_for_user("TN100004", user_id=1)
    assert p is not None
    assert p.last_change_at == when


async def test_delete_for_user_removes_history(tmp_db_path) -> None:
    from parcel_tracker.db.models import TrackingEvent

    repo = await _repo(tmp_db_path)
    await repo.create(Parcel(tracking_number="TN100006", user_id=1))
    await repo.add_events_dedup(
        "TN100006", [TrackingEvent(time="2026-01-01", description="x")], user_id=1
    )
    assert await repo.delete_for_user("TN100006", user_id=1)
    assert await repo.get_for_user("TN100006", user_id=1) is None
    assert await repo.get_history("TN100006", user_id=1) == []
    assert not await repo.delete_for_user("TN100006", user_id=1)


async def test_upgrade_backfills_last_change_at(tmp_db_path) -> None:
    await init_schema(str(tmp_db_path))
    async with aiosqlite.connect(tmp_db_path) as conn:
        await conn.execute(
            "INSERT INTO parcels (tracking_number, user_id, updated_at) "
            "VALUES ('OLD123456', 1, '2025-01-02 03:04:05')"
        )
        await conn.execute("UPDATE parcels SET last_change_at = NULL")
        await conn.commit()
    await init_schema(str(tmp_db_path))  # idempotent re-run
    p = await ParcelRepository(str(tmp_db_path)).get_for_user("OLD123456", user_id=1)
    assert p is not None
    assert p.last_change_at == datetime(2025, 1, 2, 3, 4, 5, tzinfo=UTC)


async def test_erasure_covers_settings_sessions_and_tokens(tmp_db_path) -> None:
    await init_schema(str(tmp_db_path))
    users = UserRepository(str(tmp_db_path))
    settings = SettingsRepository(str(tmp_db_path))
    web = WebRepository(str(tmp_db_path))
    await settings.set_seller_mode(5, True)
    session = await web.create_session(5, lifetime=timedelta(days=1))
    token = await web.create_api_token(5, "shop")
    assert token is not None
    await users.erase_user_data(5)
    assert not await settings.seller_mode(5)
    assert await web.get_session(session) is None
    assert await web.user_for_api_token(token) is None


def test_sql_ts_matches_sqlite_format() -> None:
    assert sql_ts(datetime(2026, 5, 6, 7, 8, 9, 123, tzinfo=UTC)) == "2026-05-06 07:08:09"
