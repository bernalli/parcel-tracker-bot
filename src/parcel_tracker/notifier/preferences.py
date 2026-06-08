"""Notification preferences: enabled gating + cooldown gate."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from parcel_tracker.db.models import ShipmentStatus
from parcel_tracker.db.notification_repository import NotificationRepository

# Every status is notified by default EXCEPT the internal NOT_FOUND "unknown"
# state. Defined by construction (not a hand-listed set) so a newly added
# ShipmentStatus member can never be silently default-OFF: the old enumerated set
# omitted EXPIRED, which 17track really emits, and those updates were dropped at
# the is_status_enabled gate even when carrying new events.
_DEFAULT_ON: frozenset[str] = frozenset(
    s.value for s in ShipmentStatus if s is not ShipmentStatus.NOT_FOUND
)


def is_default_on(status_value: str) -> bool:
    """Whether a status is notified by default, absent an explicit user pref.

    Single source of truth shared by the scheduler gate and the ``/notify`` UI so
    the menu can never show a status as "off" while the scheduler treats it as on.
    """
    return status_value in _DEFAULT_ON


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

    async def is_status_enabled(self, user_id: int, status: ShipmentStatus) -> bool:
        """True if the user wants notifications for this status (no time cooldown)."""
        if status is ShipmentStatus.NOT_FOUND:
            return False
        explicit = await self._repo.get_pref(user_id, status.value)
        return explicit if explicit is not None else (status.value in _DEFAULT_ON)

    async def mark_sent(self, user_id: int, tracking_number: str, status: ShipmentStatus) -> None:
        await self._repo.upsert_cooldown(user_id, tracking_number, status.value)
