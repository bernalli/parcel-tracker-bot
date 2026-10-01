from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from parcel_tracker.bot import callbacks
from parcel_tracker.db.migrations import init_schema
from parcel_tracker.db.models import Parcel
from parcel_tracker.db.repository import ParcelRepository


async def test_refresh_guard_is_per_user(monkeypatch: pytest.MonkeyPatch) -> None:
    import asyncio

    release = asyncio.Event()
    calls: list[int] = []

    async def slow_check(_bot_data, *, user_id, tracking_number):  # type: ignore[no-untyped-def]
        calls.append(user_id)
        await release.wait()
        return "no_change"

    monkeypatch.setitem(callbacks.__dict__, "check_parcel_now", slow_check)
    repo = AsyncMock()
    repo.get_for_user.return_value = None

    def _upd(uid: int) -> SimpleNamespace:
        return SimpleNamespace(
            callback_query=SimpleNamespace(edit_message_text=AsyncMock()),
            effective_user=SimpleNamespace(id=uid),
        )

    ctx = SimpleNamespace(bot_data={"parcel_repo": repo})
    first = asyncio.create_task(callbacks._refresh_parcel(_upd(2002), ctx, "RR123456789DE"))
    await asyncio.sleep(0)
    second = asyncio.create_task(callbacks._refresh_parcel(_upd(1001), ctx, "RR123456789DE"))
    await asyncio.sleep(0)
    release.set()
    await asyncio.gather(first, second)
    assert sorted(calls) == [1001, 2002]


async def test_readd_after_remove_reactivates(tmp_path: Path) -> None:
    db = str(tmp_path / "bot.db")
    await init_schema(db)
    repo = ParcelRepository(db)
    await repo.create(Parcel(tracking_number="RR123456789DE", user_id=1, name="Old"))
    await repo.deactivate("RR123456789DE", user_id=1)
    assert await repo.create(Parcel(tracking_number="RR123456789DE", user_id=1, name="New"))
    active = await repo.list_active_for_user(user_id=1)
    assert [(p.tracking_number, p.name) for p in active] == [("RR123456789DE", "New")]
    # an active duplicate is still reported as such
    assert await repo.create(Parcel(tracking_number="RR123456789DE", user_id=1)) is None
