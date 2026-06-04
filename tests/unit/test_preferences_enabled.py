from unittest.mock import AsyncMock, MagicMock

import pytest

from parcel_tracker.db.models import ShipmentStatus
from parcel_tracker.notifier.preferences import CooldownConfig, NotificationPreferences


@pytest.mark.asyncio
async def test_in_transit_enabled_by_default() -> None:
    repo = MagicMock()
    repo.get_pref = AsyncMock(return_value=None)
    prefs = NotificationPreferences(repo=repo, cooldown=CooldownConfig(minutes=60))
    assert await prefs.is_status_enabled(7, ShipmentStatus.IN_TRANSIT) is True
    assert await prefs.is_status_enabled(7, ShipmentStatus.NOT_FOUND) is False


@pytest.mark.asyncio
async def test_explicit_off_wins() -> None:
    repo = MagicMock()
    repo.get_pref = AsyncMock(return_value=False)
    prefs = NotificationPreferences(repo=repo, cooldown=CooldownConfig(minutes=60))
    assert await prefs.is_status_enabled(7, ShipmentStatus.IN_TRANSIT) is False
