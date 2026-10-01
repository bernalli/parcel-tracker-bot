"""Quarantine is aggregated per tracker, which /health and the gauge read (#20)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from parcel_tracker.core.health import HealthManager, QuarantineThresholds
from parcel_tracker.db.health_repository import HealthRepository
from parcel_tracker.db.migrations import get_connection, init_schema

_THRESHOLDS = QuarantineThresholds(
    level1_failures=3,
    level1_hours=1,
    level2_failures=6,
    level2_hours=6,
    level3_failures=12,
    level3_hours=24,
)


@pytest.fixture
async def manager(tmp_db_path: Path) -> HealthManager:
    await init_schema(str(tmp_db_path))
    return HealthManager(HealthRepository(str(tmp_db_path)), thresholds=_THRESHOLDS)


@pytest.mark.asyncio
async def test_outage_across_many_shipments_trips_the_tracker(manager: HealthManager) -> None:
    # One failure each on 100 different shipments: no shipment reaches its own
    # threshold, but the tracker is plainly down.
    for i in range(100):
        await manager.record_failure("ups", f"1Z{i:016d}")

    assert await manager.is_tracker_quarantined("ups")
    assert await manager.is_quarantined("ups", "1ZNEVERSEEN000000")
    state = await manager.repo.get_state("ups", "")
    assert state is not None
    assert state.total_checks == 100
    assert state.total_failures == 100


@pytest.mark.asyncio
async def test_a_few_unknown_codes_do_not_trip_the_tracker(manager: HealthManager) -> None:
    for i in range(_THRESHOLDS.level1_failures * 4 - 1):
        await manager.record_failure("ups", f"1Z{i:016d}")
    assert not await manager.is_tracker_quarantined("ups")


@pytest.mark.asyncio
async def test_success_on_any_shipment_resets_the_tracker_count(manager: HealthManager) -> None:
    for i in range(10):
        await manager.record_failure("ups", f"1Z{i:016d}")
    await manager.record_success("ups", "1ZOK0000000000000")
    for i in range(10):
        await manager.record_failure("ups", f"1Y{i:016d}")
    assert not await manager.is_tracker_quarantined("ups")
    state = await manager.repo.get_state("ups", "")
    assert state is not None
    assert state.total_checks == 21


@pytest.mark.asyncio
async def test_failures_outside_the_window_start_over(
    manager: HealthManager, tmp_db_path: Path
) -> None:
    for i in range(11):
        await manager.record_failure("ups", f"1Z{i:016d}")
    old = (datetime.now(UTC) - timedelta(hours=2)).strftime("%Y-%m-%d %H:%M:%S")
    async with get_connection(str(tmp_db_path)) as conn:
        await conn.execute(
            "UPDATE tracker_health SET last_failure_at = ? WHERE tracking_id = ''", (old,)
        )
        await conn.commit()
    await manager.record_failure("ups", "1ZLATE00000000000")
    state = await manager.repo.get_state("ups", "")
    assert state is not None
    assert state.consecutive_failures == 1
    assert not await manager.is_tracker_quarantined("ups")


@pytest.mark.asyncio
async def test_health_command_shows_aggregate_data(manager: HealthManager) -> None:
    from parcel_tracker.bot.health_commands import cmd_health

    await manager.record_success("ups", "1Z0000000000000001")
    await manager.record_failure("ups", "1Z0000000000000002")

    tracker = MagicMock()
    tracker.name = "ups"
    registry = MagicMock()
    registry.iter_all.return_value = [tracker]
    message = MagicMock()
    sent: list[str] = []

    async def _reply(text: str, **_kw: object) -> None:
        sent.append(text)

    message.reply_text = _reply
    update = MagicMock()
    update.effective_message = message
    context = MagicMock()
    context.bot_data = {"registry": registry, "health_repo": manager.repo}

    await cmd_health(update, context)

    assert "no data yet" not in sent[0]
    assert "50%" in sent[0]
