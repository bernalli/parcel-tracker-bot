"""Tests for NotificationRepository: prefs CRUD + cooldown log."""

from __future__ import annotations

from datetime import UTC

import pytest

from parcel_tracker.db.migrations import init_schema
from parcel_tracker.db.notification_repository import NotificationRepository


@pytest.mark.asyncio
async def test_get_pref_returns_none_when_unset(tmp_path) -> None:
    db = str(tmp_path / "n.db")
    await init_schema(db)
    repo = NotificationRepository(db)
    assert await repo.get_pref(user_id=1, status_value="Delivered") is None


@pytest.mark.asyncio
async def test_set_and_get_pref(tmp_path) -> None:
    db = str(tmp_path / "n.db")
    await init_schema(db)
    repo = NotificationRepository(db)
    await repo.set_pref(user_id=1, status_value="Delivered", enabled=True)
    assert await repo.get_pref(user_id=1, status_value="Delivered") is True
    await repo.set_pref(user_id=1, status_value="Delivered", enabled=False)
    assert await repo.get_pref(user_id=1, status_value="Delivered") is False


@pytest.mark.asyncio
async def test_get_all_prefs_returns_dict(tmp_path) -> None:
    db = str(tmp_path / "n.db")
    await init_schema(db)
    repo = NotificationRepository(db)
    await repo.set_pref(user_id=1, status_value="Delivered", enabled=True)
    await repo.set_pref(user_id=1, status_value="Exception", enabled=False)
    prefs = await repo.get_all_prefs(user_id=1)
    assert prefs == {"Delivered": True, "Exception": False}


@pytest.mark.asyncio
async def test_upsert_and_get_cooldown(tmp_path) -> None:
    db = str(tmp_path / "n.db")
    await init_schema(db)
    repo = NotificationRepository(db)
    assert await repo.get_last_sent(1, "ABC", "Delivered") is None
    await repo.upsert_cooldown(1, "ABC", "Delivered")
    sent = await repo.get_last_sent(1, "ABC", "Delivered")
    assert sent is not None
    assert sent.tzinfo is UTC


@pytest.mark.asyncio
async def test_upsert_cooldown_overwrites_sent_at(tmp_path) -> None:
    """A second upsert refreshes sent_at to current time."""
    import asyncio

    db = str(tmp_path / "n.db")
    await init_schema(db)
    repo = NotificationRepository(db)
    await repo.upsert_cooldown(1, "ABC", "Delivered")
    first = await repo.get_last_sent(1, "ABC", "Delivered")
    await asyncio.sleep(0.01)
    await repo.upsert_cooldown(1, "ABC", "Delivered")
    second = await repo.get_last_sent(1, "ABC", "Delivered")
    assert second is not None and first is not None
    assert second >= first
