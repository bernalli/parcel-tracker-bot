"""Tests for /health, /health <name>, /health reset commands."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest

from parcel_tracker.bot.health_commands import (
    cmd_health,
    cmd_health_detail,
    cmd_health_reset,
    compute_color_emoji,
)


def test_compute_color_quarantined_returns_red() -> None:
    until = datetime.now(UTC) + timedelta(minutes=10)
    assert compute_color_emoji(success_rate=1.0, quarantine_until=until) == "🔴"


def test_compute_color_high_success_returns_green() -> None:
    assert compute_color_emoji(success_rate=0.99, quarantine_until=None) == "🟢"


def test_compute_color_mid_returns_yellow() -> None:
    assert compute_color_emoji(success_rate=0.85, quarantine_until=None) == "🟡"


def test_compute_color_low_returns_red() -> None:
    assert compute_color_emoji(success_rate=0.5, quarantine_until=None) == "🔴"


@pytest.mark.asyncio
async def test_cmd_health_lists_all_registered_trackers() -> None:
    """`/health` lists every tracker from registry, even with no DB row."""
    fake_dhl = MagicMock()
    fake_dhl.name = "dhl"
    fake_track17 = MagicMock()
    fake_track17.name = "track17"

    registry = MagicMock()
    registry.iter_all = MagicMock(return_value=iter([fake_dhl, fake_track17]))

    health_repo = MagicMock()
    health_repo.get_state = AsyncMock(return_value=None)

    update = MagicMock()
    update.effective_chat.id = 1
    update.message.reply_text = AsyncMock()

    context = MagicMock()
    context.bot_data = {
        "registry": registry,
        "health_repo": health_repo,
        "config": MagicMock(admin_user_ids=frozenset()),
    }

    await cmd_health(update, context)

    update.message.reply_text.assert_awaited_once()
    text = update.message.reply_text.call_args.args[0]
    assert "dhl" in text
    assert "track17" in text
    assert "🟢" in text
    assert "no data yet" in text.lower()


@pytest.mark.asyncio
async def test_cmd_health_detail_shows_metrics() -> None:
    from parcel_tracker.db.health_repository import HealthState

    state = HealthState(
        tracker_id="dhl",
        tracking_id="",
        last_success_at=datetime(2026, 5, 9, 12, 0, tzinfo=UTC),
        last_failure_at=None,
        consecutive_failures=0,
        consecutive_successes=10,
        quarantine_until=None,
        total_checks=100,
        total_failures=2,
    )
    health_repo = MagicMock()
    health_repo.get_state = AsyncMock(return_value=state)

    registry = MagicMock()
    fake_dhl = MagicMock()
    fake_dhl.name = "dhl"
    registry.iter_all = MagicMock(return_value=iter([fake_dhl]))

    update = MagicMock()
    update.message.reply_text = AsyncMock()
    context = MagicMock()
    context.bot_data = {
        "registry": registry,
        "health_repo": health_repo,
        "config": MagicMock(admin_user_ids=frozenset()),
    }
    context.args = ["dhl"]

    await cmd_health_detail(update, context)
    text = update.message.reply_text.call_args.args[0]
    assert "dhl" in text
    assert "98" in text  # 98% success rate
    assert "100" in text  # total_checks


@pytest.mark.asyncio
async def test_cmd_health_reset_admin_only() -> None:
    update = MagicMock()
    update.effective_user.id = 999
    update.message.reply_text = AsyncMock()
    context = MagicMock()
    context.bot_data = {
        "config": MagicMock(admin_user_ids=frozenset({1, 2})),
        "health_repo": MagicMock(),
    }
    context.args = ["dhl"]

    await cmd_health_reset(update, context)
    text = update.message.reply_text.call_args.args[0]
    assert "admin" in text.lower()


@pytest.mark.asyncio
async def test_cmd_health_reset_calls_repo_reset() -> None:
    health_repo = MagicMock()
    health_repo.reset_tracker = AsyncMock()

    update = MagicMock()
    update.effective_user.id = 1
    update.message.reply_text = AsyncMock()
    context = MagicMock()
    context.bot_data = {
        "config": MagicMock(admin_user_ids=frozenset({1})),
        "health_repo": health_repo,
    }
    context.args = ["dhl"]

    await cmd_health_reset(update, context)
    health_repo.reset_tracker.assert_awaited_once_with("dhl")
