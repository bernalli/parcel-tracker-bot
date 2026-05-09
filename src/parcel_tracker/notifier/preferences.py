"""Notification preferences: enabled gating + cooldown gate."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from parcel_tracker.db.models import ShipmentStatus
from parcel_tracker.db.notification_repository import NotificationRepository

_DEFAULT_ON: frozenset[str] = frozenset(
    {
        ShipmentStatus.DELIVERED.value,
        ShipmentStatus.EXCEPTION.value,
        ShipmentStatus.OUT_FOR_DELIVERY.value,
        ShipmentStatus.RETURNED.value,
    }
)


@dataclass(frozen=True, slots=True)
class CooldownConfig:
    minutes: int


class NotificationPreferences:
    """Resolve whether a notification is allowed given user prefs + cooldown."""

    def __init__(
        self,
        repo: NotificationRepository,
        cooldown: CooldownConfig,
    ) -> None:
        self._repo = repo
        self._cooldown = cooldown

    async def is_allowed(self, user_id: int, status: ShipmentStatus, tracking_number: str) -> bool:
        # NOT_FOUND is never notified.
        if status is ShipmentStatus.NOT_FOUND:
            return False

        explicit = await self._repo.get_pref(user_id, status.value)
        enabled = explicit if explicit is not None else (status.value in _DEFAULT_ON)
        if not enabled:
            return False

        last = await self._repo.get_last_sent(user_id, tracking_number, status.value)
        if last is None:
            return True
        return datetime.now(UTC) >= last + timedelta(minutes=self._cooldown.minutes)

    async def mark_sent(self, user_id: int, tracking_number: str, status: ShipmentStatus) -> None:
        await self._repo.upsert_cooldown(user_id, tracking_number, status.value)
