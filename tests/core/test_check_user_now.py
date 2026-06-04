# tests/core/test_check_user_now.py
from __future__ import annotations

import pytest

from parcel_tracker.core import scheduler


@pytest.mark.asyncio
async def test_check_user_now_checks_all_active_ignoring_due(monkeypatch) -> None:
    from parcel_tracker.db.models import Parcel

    parcels = [Parcel(tracking_number="A", user_id=10), Parcel(tracking_number="B", user_id=10)]

    class _Repo:
        async def list_active_for_user(self, *, user_id):
            return parcels

    checked = []

    async def fake_check_one(**kwargs):
        checked.append(kwargs["parcel"].tracking_number)

    monkeypatch.setattr(scheduler, "_check_one", fake_check_one)
    bot_data = {
        "parcel_repo": _Repo(),
        "detector": object(),
        "health": object(),
        "notifier": object(),
        "rate_limiter": object(),
        "prefs": None,
        "geocoder": None,
        "map_renderer": None,
        "config": type("C", (), {"batch_size": 10})(),
    }
    count = await scheduler.check_user_now(bot_data, user_id=10)
    assert count == 2
    assert set(checked) == {"A", "B"}
