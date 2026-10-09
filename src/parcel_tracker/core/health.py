"""Tracker health management: escalation thresholds + health_aware decorator."""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, replace
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


# The tracker-wide circuit needs more evidence than one shipment: a few codes the
# carrier does not know yet must not quarantine the tracker for everyone.
AGGREGATE_FAILURE_MULTIPLIER = 4
# Failures further apart than this do not add up to an outage.
AGGREGATE_WINDOW = timedelta(minutes=30)


def _scaled(thresholds: QuarantineThresholds, factor: int) -> QuarantineThresholds:
    return replace(
        thresholds,
        level1_failures=thresholds.level1_failures * factor,
        level2_failures=thresholds.level2_failures * factor,
        level3_failures=thresholds.level3_failures * factor,
    )


class HealthManager:
    """
    Coordinates health tracking with quarantine escalation.

    Health is kept at two levels:

    - per shipment ``(tracker, tracking_id)``: diagnostics and a per-code
      quarantine, escalating at ``thresholds`` (3/6/12 consecutive failures);
    - per tracker ``(tracker, "")``: the aggregate circuit that ``/health`` and the
      ``parceltracker_quarantine_active`` gauge read. Every shipment's result also
      updates it; it trips at ``aggregate_thresholds`` (default 4x the per-shipment
      ones) of consecutive failures across shipments, where a gap longer than
      ``aggregate_window`` since the last failure starts the count again.

    On success, consecutive_failures is reset and quarantine_until cleared, at both
    levels.
    """

    def __init__(
        self,
        repo: HealthRepository,
        *,
        thresholds: QuarantineThresholds,
        aggregate_thresholds: QuarantineThresholds | None = None,
        aggregate_window: timedelta = AGGREGATE_WINDOW,
    ) -> None:
        self.repo = repo
        self.thresholds = thresholds
        self.aggregate_thresholds = aggregate_thresholds or _scaled(
            thresholds, AGGREGATE_FAILURE_MULTIPLIER
        )
        self.aggregate_window = aggregate_window

    async def record_success(self, tracker_id: str, tracking_id: str = "") -> None:
        await self.repo.record_success(tracker_id, tracking_id)
        if tracking_id:
            await self.repo.record_success(tracker_id, "")

    async def record_failure(self, tracker_id: str, tracking_id: str = "") -> None:
        if not tracking_id:
            await self._record_failure_at(tracker_id, "", self.thresholds)
            return
        await self._record_failure_at(tracker_id, tracking_id, self.thresholds)
        aggregate = await self.repo.get_state(tracker_id, "")
        if (
            aggregate is not None
            and aggregate.last_failure_at is not None
            and datetime.now(UTC) - aggregate.last_failure_at > self.aggregate_window
        ):
            await self.repo.reset_consecutive(tracker_id, "")
        await self._record_failure_at(tracker_id, "", self.aggregate_thresholds)

    async def record_not_found(self, tracker_id: str, tracking_id: str) -> None:
        """The carrier does not know this code (yet): back off this code only.

        An unscanned label is not an outage, so it never feeds the tracker-wide
        circuit (a seller adding a dozen fresh labels must not quarantine the
        carrier for everyone), and its own back-off is capped at the first tier so
        the first real scan is picked up within ``level1_hours``.
        """
        t = self.thresholds
        capped = QuarantineThresholds(
            level1_failures=t.level1_failures,
            level1_hours=t.level1_hours,
            level2_failures=t.level2_failures,
            level2_hours=t.level1_hours,
            level3_failures=t.level3_failures,
            level3_hours=t.level1_hours,
        )
        await self._record_failure_at(tracker_id, tracking_id, capped)

    async def is_tracker_quarantined(self, tracker_id: str) -> bool:
        """True when the tracker-wide circuit is open (all shipments skipped)."""
        return await self.repo.is_quarantined(tracker_id, "")

    async def _record_failure_at(
        self, tracker_id: str, tracking_id: str, thresholds: QuarantineThresholds
    ) -> None:
        await self.repo.record_failure(tracker_id, tracking_id)
        state = await self.repo.get_state(tracker_id, tracking_id)
        if state is None:
            return

        hours = self._compute_quarantine_hours(state.consecutive_failures, thresholds)
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

    def _compute_quarantine_hours(
        self, consecutive_failures: int, thresholds: QuarantineThresholds | None = None
    ) -> int:
        t = thresholds or self.thresholds
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
