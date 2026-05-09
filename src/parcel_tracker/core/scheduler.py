"""Periodic tracking job — checks active parcels with dynamic interval, parallel batch,
and per-tracker rate limiting."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any, Protocol

from parcel_tracker.core.detector import CourierDetector
from parcel_tracker.core.health import HealthManager
from parcel_tracker.core.rate_limiter import RateLimiter
from parcel_tracker.core.status_intervals import is_due
from parcel_tracker.db.models import Parcel, ShipmentStatus
from parcel_tracker.db.repository import ParcelRepository
from parcel_tracker.notifier.telegram import TelegramNotifier
from parcel_tracker.observability.metrics import (
    CHECK_LATENCY_SECONDS,
    CHECK_TOTAL,
    QUARANTINE_ACTIVE,
    SCHEDULER_TICK_DURATION_SECONDS,
)

logger = logging.getLogger(__name__)


PRIORITY_ORDER: list[ShipmentStatus] = [
    ShipmentStatus.OUT_FOR_DELIVERY,
    ShipmentStatus.IN_TRANSIT,
    ShipmentStatus.CUSTOMS,
    ShipmentStatus.PICKUP,
    ShipmentStatus.UNDELIVERED,
    ShipmentStatus.EXCEPTION,
    ShipmentStatus.ALERT,
    ShipmentStatus.INFO_RECEIVED,
    ShipmentStatus.RETURNED,
    ShipmentStatus.NOT_FOUND,
]


def sort_by_priority(parcels: list[Parcel]) -> list[Parcel]:
    """Sort parcels descending by urgency (OUT_FOR_DELIVERY first, NOT_FOUND last)."""
    rank = {status: idx for idx, status in enumerate(PRIORITY_ORDER)}
    return sorted(parcels, key=lambda p: rank.get(p.status, 999))


class _JobContext(Protocol):
    bot_data: dict[str, Any]


def _now_default() -> datetime:
    return datetime.now(UTC)


def _chunked(seq: list[tuple[int, Parcel]], size: int) -> list[list[tuple[int, Parcel]]]:
    return [seq[i : i + size] for i in range(0, len(seq), size)]


async def check_updates(context: _JobContext) -> None:
    """Periodic job: instrumented entry point. Wraps body with scheduler tick histogram."""
    with SCHEDULER_TICK_DURATION_SECONDS.time():
        await _check_updates_impl(context)


async def _check_updates_impl(context: _JobContext) -> None:
    """Filter due parcels, sort by priority, process in parallel batches.

    bot_data keys consumed:
      - parcel_repo, user_repo, registry, detector, health, notifier (existing)
      - config: provides batch_size
      - rate_limiter: RateLimiter instance
      - prefs: NotificationPreferences instance for gating, OR None if not wired
          (when None, gating is bypassed and notifications go through always)
      - now (test-only optional): zero-arg callable returning current datetime
    """
    parcel_repo: ParcelRepository = context.bot_data["parcel_repo"]
    user_repo = context.bot_data["user_repo"]
    detector: CourierDetector = context.bot_data["detector"]
    health: HealthManager = context.bot_data["health"]
    notifier: TelegramNotifier = context.bot_data["notifier"]
    config = context.bot_data["config"]
    rate_limiter: RateLimiter = context.bot_data["rate_limiter"]
    prefs = context.bot_data.get("prefs")  # None until NotificationPreferences is wired
    now: Callable[[], datetime] = context.bot_data.get("now", _now_default)

    user_ids = await user_repo.get_allowed_user_ids()
    if not user_ids:
        return

    all_due: list[tuple[int, Parcel]] = []
    for user_id in user_ids:
        parcels = await parcel_repo.list_active_for_user(user_id=user_id)
        for parcel in parcels:
            if is_due(parcel.status, parcel.last_check_at, now()):
                all_due.append((user_id, parcel))

    if not all_due:
        return

    rank = {status: idx for idx, status in enumerate(PRIORITY_ORDER)}
    all_due.sort(key=lambda pair: rank.get(pair[1].status, 999))

    batch_size = int(getattr(config, "batch_size", 10))
    for batch in _chunked(all_due, batch_size):
        await asyncio.gather(
            *[
                _check_one(
                    parcel=p,
                    user_id=uid,
                    parcel_repo=parcel_repo,
                    detector=detector,
                    health=health,
                    notifier=notifier,
                    rate_limiter=rate_limiter,
                    prefs=prefs,
                    now=now,
                )
                for (uid, p) in batch
            ],
            return_exceptions=True,
        )


async def _check_one(  # noqa: PLR0913
    *,
    parcel: Parcel,
    user_id: int,
    parcel_repo: ParcelRepository,
    detector: CourierDetector,
    health: HealthManager,
    notifier: TelegramNotifier,
    rate_limiter: RateLimiter,
    prefs: Any | None,
    now: Callable[[], datetime],
) -> None:
    """Check a single parcel: rate limit, fetch, record health, notify if status changed."""
    matches = detector.detect(parcel.tracking_number)
    if not matches:
        logger.debug("No tracker matches for %s", parcel.tracking_number)
        return

    tracker = matches[0]

    if await health.is_quarantined(tracker.name, parcel.tracking_number):
        logger.debug(
            "Skipping %s/%s — quarantined",
            tracker.name,
            parcel.tracking_number,
        )
        QUARANTINE_ACTIVE.labels(tracker=tracker.name).set(1)
        CHECK_TOTAL.labels(tracker=tracker.name, outcome="quarantined").inc()
        return

    QUARANTINE_ACTIVE.labels(tracker=tracker.name).set(0)
    await rate_limiter.acquire(tracker.name)

    try:
        with CHECK_LATENCY_SECONDS.labels(tracker=tracker.name).time():
            result = await tracker.fetch(parcel.tracking_number)
    except Exception as exc:  # noqa: BLE001 (instrumentation)
        logger.warning(
            "Tracker %s failed for %s: %s",
            tracker.name,
            parcel.tracking_number,
            exc,
        )
        CHECK_TOTAL.labels(tracker=tracker.name, outcome="failure").inc()
        await health.record_failure(tracker.name, parcel.tracking_number)
        await parcel_repo.set_last_check_at(parcel.tracking_number, now())
        return

    if not result.found:
        CHECK_TOTAL.labels(tracker=tracker.name, outcome="failure").inc()
        await health.record_failure(tracker.name, parcel.tracking_number)
        await parcel_repo.set_last_check_at(parcel.tracking_number, now())
        return

    CHECK_TOTAL.labels(tracker=tracker.name, outcome="success").inc()
    await health.record_success(tracker.name, parcel.tracking_number)
    await parcel_repo.set_last_check_at(parcel.tracking_number, now())

    if result.status != parcel.status:
        await parcel_repo.update_status(parcel.tracking_number, result.status)
        gated = prefs is None or await prefs.is_allowed(
            user_id, result.status, parcel.tracking_number
        )
        if gated:
            last_event = result.events[0] if result.events else None
            await notifier.send_status_update(
                chat_id=user_id,
                tracking_number=parcel.tracking_number,
                parcel_name=parcel.name,
                old_status=parcel.status,
                new_status=result.status,
                last_event=last_event,
            )
            if prefs is not None:
                await prefs.mark_sent(user_id, parcel.tracking_number, result.status)
