"""Periodic tracking job — checks active parcels for updates."""

from __future__ import annotations

import logging
from typing import Any, Protocol

from parcel_tracker.core.detector import CourierDetector
from parcel_tracker.core.health import HealthManager
from parcel_tracker.core.registry import TrackerRegistry
from parcel_tracker.db.models import Parcel, ShipmentStatus
from parcel_tracker.db.repository import ParcelRepository
from parcel_tracker.notifier.telegram import TelegramNotifier

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


async def check_updates(context: _JobContext) -> None:
    """Periodic job: iterate all active parcels and refresh status."""
    parcel_repo = context.bot_data["parcel_repo"]
    registry = context.bot_data["registry"]
    detector = context.bot_data["detector"]
    health = context.bot_data["health"]
    notifier = context.bot_data["notifier"]
    user_repo = context.bot_data["user_repo"]

    user_ids = await user_repo.get_allowed_user_ids()

    for user_id in user_ids:
        parcels = await parcel_repo.list_active_for_user(user_id=user_id)
        for parcel in parcels:
            await _check_one(parcel, parcel_repo, registry, detector, health, notifier, user_id)


async def _check_one(  # noqa: PLR0913
    parcel: Parcel,
    parcel_repo: ParcelRepository,
    registry: TrackerRegistry,
    detector: CourierDetector,
    health: HealthManager,
    notifier: TelegramNotifier,
    user_id: int,
) -> None:
    """Check a single parcel for status updates."""
    matches = detector.detect(parcel.tracking_number)
    if not matches:
        logger.debug("No tracker matches for %s", parcel.tracking_number)
        return

    tracker = matches[0]

    if await health.is_quarantined(tracker.name, parcel.tracking_number):
        logger.debug(
            "Skipping %s/%s — currently quarantined",
            tracker.name,
            parcel.tracking_number,
        )
        return

    try:
        result = await tracker.fetch(parcel.tracking_number)
    except Exception as exc:  # noqa: BLE001 (instrumentation)
        logger.warning(
            "Tracker %s failed for %s: %s",
            tracker.name,
            parcel.tracking_number,
            exc,
        )
        await health.record_failure(tracker.name, parcel.tracking_number)
        return

    if not result.found:
        await health.record_failure(tracker.name, parcel.tracking_number)
        return

    await health.record_success(tracker.name, parcel.tracking_number)

    if result.status != parcel.status:
        await parcel_repo.update_status(parcel.tracking_number, result.status)
        last_event = result.events[0] if result.events else None
        await notifier.send_status_update(
            chat_id=user_id,
            tracking_number=parcel.tracking_number,
            parcel_name=parcel.name,
            old_status=parcel.status,
            new_status=result.status,
            last_event=last_event,
        )
