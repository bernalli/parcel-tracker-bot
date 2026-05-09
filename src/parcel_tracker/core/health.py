"""Tracker health management: escalation thresholds + health_aware decorator."""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import TypeVar

from parcel_tracker.db.health_repository import HealthRepository

logger = logging.getLogger(__name__)

T = TypeVar("T")


@dataclass(frozen=True, slots=True)
class QuarantineThresholds:
    level1_failures: int
    level1_hours: int
    level2_failures: int
    level2_hours: int
    level3_failures: int
    level3_hours: int


class HealthManager:
    """
    Coordinates health tracking with quarantine escalation.

    On each failure, increments consecutive_failures via repo and applies
    quarantine when thresholds are crossed:
      - 3 failures consecutive → 1h quarantine
      - 6 failures consecutive → 6h quarantine
      - 12 failures consecutive → 24h quarantine

    On success, resets consecutive_failures and clears quarantine_until.
    """

    def __init__(
        self,
        repo: HealthRepository,
        *,
        thresholds: QuarantineThresholds,
    ) -> None:
        self.repo = repo
        self.thresholds = thresholds

    async def record_success(self, tracker_id: str, tracking_id: str = "") -> None:
        await self.repo.record_success(tracker_id, tracking_id)

    async def record_failure(self, tracker_id: str, tracking_id: str = "") -> None:
        await self.repo.record_failure(tracker_id, tracking_id)
        state = await self.repo.get_state(tracker_id, tracking_id)
        if state is None:
            return

        hours = self._compute_quarantine_hours(state.consecutive_failures)
        if hours > 0:
            until = datetime.now(UTC) + timedelta(hours=hours)
            await self.repo.set_quarantine(tracker_id, tracking_id, until)
            logger.warning(
                "Tracker %s/%s quarantined for %dh (consecutive_failures=%d)",
                tracker_id,
                tracking_id or "<global>",
                hours,
                state.consecutive_failures,
            )

    async def is_quarantined(self, tracker_id: str, tracking_id: str = "") -> bool:
        # Check specific tracking_id first; also check global ("") entry which
        # acts as a tracker-wide quarantine gate (any tracking_id is blocked).
        if tracking_id and await self.repo.is_quarantined(tracker_id, ""):
            return True
        return await self.repo.is_quarantined(tracker_id, tracking_id)

    def _compute_quarantine_hours(self, consecutive_failures: int) -> int:
        t = self.thresholds
        if consecutive_failures >= t.level3_failures:
            return t.level3_hours
        if consecutive_failures >= t.level2_failures:
            return t.level2_hours
        if consecutive_failures >= t.level1_failures:
            return t.level1_hours
        return 0


def health_aware(
    *,
    manager: HealthManager,
    tracker_id: str,
) -> Callable[[Callable[..., Awaitable[T]]], Callable[..., Awaitable[T | None]]]:
    """
    Decorator: skip the wrapped fetch call if the tracker is quarantined.

    Records success/failure based on whether the call raised an exception.
    Intentionally catches any Exception (broad catch) — this is a top-level
    instrumentation point where all failures, regardless of type, should be
    counted against the tracker's health score.
    """

    def decorator(
        fn: Callable[..., Awaitable[T]],
    ) -> Callable[..., Awaitable[T | None]]:
        async def wrapper(tracking_id: str = "", *args: object, **kwargs: object) -> T | None:
            if await manager.is_quarantined(tracker_id, tracking_id):
                logger.debug(
                    "Skipping %s/%s — currently quarantined",
                    tracker_id,
                    tracking_id or "<global>",
                )
                return None
            try:
                result = await fn(tracking_id, *args, **kwargs)
            except Exception:  # noqa: BLE001 — instrumentation: any exception counts as failure
                await manager.record_failure(tracker_id, tracking_id)
                raise
            else:
                await manager.record_success(tracker_id, tracking_id)
                return result

        return wrapper

    return decorator
