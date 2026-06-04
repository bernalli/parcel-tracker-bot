# tests/bot/test_cmd_stats.py
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from parcel_tracker.bot import admin_commands
from parcel_tracker.db.models import Parcel, ShipmentStatus


@pytest.mark.asyncio
async def test_stats_counts_owner_and_parcels() -> None:
    parcel_repo = AsyncMock()
    parcel_repo.list_active_for_user.return_value = [
        Parcel(
            tracking_number="A", user_id=10, carrier_name="UPS", status=ShipmentStatus.IN_TRANSIT
        ),
        Parcel(
            tracking_number="B",
            user_id=10,
            carrier_name="DHL",
            status=ShipmentStatus.OUT_FOR_DELIVERY,
        ),
    ]
    parcel_repo.list_archived_for_user.return_value = [
        Parcel(
            tracking_number="C", user_id=10, carrier_name="UPS", status=ShipmentStatus.DELIVERED
        ),
    ]
    parcel_repo.count_events_for_user.return_value = 42
    user_repo = AsyncMock()
    user_repo.get_allowed_user_ids.return_value = []  # owner not in table
    health_repo = AsyncMock()
    health_repo.count_quarantined.return_value = 1

    reply = AsyncMock()
    update = SimpleNamespace(
        effective_user=SimpleNamespace(id=10),
        effective_message=SimpleNamespace(reply_text=reply),
    )
    config = SimpleNamespace(owner_id=10, allowed_user_ids=(), check_interval_minutes=30)
    context = SimpleNamespace(
        bot_data={
            "parcel_repo": parcel_repo,
            "user_repo": user_repo,
            "health_repo": health_repo,
            "config": config,
            "registry": ["t"] * 24,
        }
    )
    await admin_commands.cmd_stats(update, context)
    text = reply.await_args.args[0]
    assert "1" in text  # owner counted (not 0)
    assert "Utenti" in text or "users" in text.lower()
    assert "UPS" in text and "DHL" in text
    assert "42" in text  # events
