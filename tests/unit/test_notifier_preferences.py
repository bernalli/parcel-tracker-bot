"""Tests for NotificationPreferences (defaults + cooldown logic)."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest
from freezegun import freeze_time

from parcel_tracker.db.models import ShipmentStatus
from parcel_tracker.notifier.preferences import (
    CooldownConfig,
    NotificationPreferences,
)


def _make_repo(*, get_pref_returns=None, get_last_sent_returns=None):
    repo = MagicMock()
    repo.get_pref = AsyncMock(return_value=get_pref_returns)
    repo.get_last_sent = AsyncMock(return_value=get_last_sent_returns)
    repo.upsert_cooldown = AsyncMock()
    return repo


@pytest.mark.asyncio
async def test_is_allowed_default_on_for_delivered() -> None:
    repo = _make_repo(get_pref_returns=None, get_last_sent_returns=None)
    prefs = NotificationPreferences(repo=repo, cooldown=CooldownConfig(minutes=60))
    assert await prefs.is_allowed(1, ShipmentStatus.DELIVERED, "ABC") is True


@pytest.mark.asyncio
async def test_is_allowed_default_on_for_in_transit() -> None:
    # IN_TRANSIT is now default-on (user complained in-transit updates were silent).
    repo = _make_repo(get_pref_returns=None, get_last_sent_returns=None)
    prefs = NotificationPreferences(repo=repo, cooldown=CooldownConfig(minutes=60))
    assert await prefs.is_allowed(1, ShipmentStatus.IN_TRANSIT, "ABC") is True


@pytest.mark.asyncio
async def test_is_allowed_explicit_pref_overrides_default() -> None:
    repo = _make_repo(get_pref_returns=False, get_last_sent_returns=None)
    prefs = NotificationPreferences(repo=repo, cooldown=CooldownConfig(minutes=60))
    assert await prefs.is_allowed(1, ShipmentStatus.DELIVERED, "ABC") is False


@pytest.mark.asyncio
async def test_is_allowed_explicit_true_enables_pickup() -> None:
    # Explicit pref=True allows notification even when default would also allow it.
    repo = _make_repo(get_pref_returns=True, get_last_sent_returns=None)
    prefs = NotificationPreferences(repo=repo, cooldown=CooldownConfig(minutes=60))
    assert await prefs.is_allowed(1, ShipmentStatus.PICKUP, "ABC") is True


@pytest.mark.asyncio
@freeze_time("2026-05-09 12:00:00")
async def test_is_allowed_blocked_within_cooldown() -> None:
    last = datetime(2026, 5, 9, 11, 30, tzinfo=UTC)  # 30 min ago, cooldown=60
    repo = _make_repo(get_pref_returns=True, get_last_sent_returns=last)
    prefs = NotificationPreferences(repo=repo, cooldown=CooldownConfig(minutes=60))
    assert await prefs.is_allowed(1, ShipmentStatus.DELIVERED, "ABC") is False


@pytest.mark.asyncio
@freeze_time("2026-05-09 12:00:00")
async def test_is_allowed_passes_after_cooldown() -> None:
    last = datetime(2026, 5, 9, 10, 30, tzinfo=UTC)  # 90 min ago, cooldown=60
    repo = _make_repo(get_pref_returns=True, get_last_sent_returns=last)
    prefs = NotificationPreferences(repo=repo, cooldown=CooldownConfig(minutes=60))
    assert await prefs.is_allowed(1, ShipmentStatus.DELIVERED, "ABC") is True


@pytest.mark.asyncio
async def test_mark_sent_calls_upsert_cooldown() -> None:
    repo = _make_repo(get_pref_returns=None, get_last_sent_returns=None)
    prefs = NotificationPreferences(repo=repo, cooldown=CooldownConfig(minutes=60))
    await prefs.mark_sent(1, "ABC", ShipmentStatus.DELIVERED)
    repo.upsert_cooldown.assert_awaited_once_with(1, "ABC", "Delivered")


@pytest.mark.asyncio
async def test_is_allowed_not_found_always_false() -> None:
    repo = _make_repo(get_pref_returns=True, get_last_sent_returns=None)
    prefs = NotificationPreferences(repo=repo, cooldown=CooldownConfig(minutes=60))
    assert await prefs.is_allowed(1, ShipmentStatus.NOT_FOUND, "ABC") is False
