"""Periodic tracking job — checks active parcels with dynamic interval, parallel batch,
and per-tracker rate limiting."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any, Protocol

from parcel_tracker.core.detector import CourierDetector
from parcel_tracker.core.event_status import status_from_text
from parcel_tracker.core.health import HealthManager
from parcel_tracker.core.rate_limiter import RateLimiter
from parcel_tracker.core.status_intervals import is_due
from parcel_tracker.core.tracker_base import TrackingResult
from parcel_tracker.db.models import Parcel, ShipmentStatus, TrackingEvent
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


async def check_user_now(bot_data: dict[str, Any], *, user_id: int) -> int:
    """On-demand: check ALL active parcels for a user immediately (ignores is_due).
    Returns the number of parcels checked. Reuses _check_one."""
    parcel_repo: ParcelRepository = bot_data["parcel_repo"]
    parcels = await parcel_repo.list_active_for_user(user_id=user_id)
    if not parcels:
        return 0
    batch_size = int(getattr(bot_data["config"], "batch_size", 10))
    for batch in _chunked([(user_id, p) for p in parcels], batch_size):
        await asyncio.gather(
            *[
                _check_one(
                    parcel=p,
                    user_id=uid,
                    parcel_repo=parcel_repo,
                    detector=bot_data["detector"],
                    health=bot_data["health"],
                    notifier=bot_data["notifier"],
                    rate_limiter=bot_data["rate_limiter"],
                    prefs=bot_data.get("prefs"),
                    geocoder=bot_data.get("geocoder"),
                    map_renderer=bot_data.get("map_renderer"),
                    now=bot_data.get("now", _now_default),
                )
                for (uid, p) in batch
            ],
            return_exceptions=True,
        )
    return len(parcels)


async def check_updates(context: _JobContext) -> None:
    """Periodic job: instrumented entry point. Wraps body with scheduler tick histogram."""
    with SCHEDULER_TICK_DURATION_SECONDS.time():
        await _check_updates_impl(context)


async def _check_updates_impl(context: _JobContext) -> None:
    """Filter due parcels, sort by priority, process in parallel batches.

    bot_data keys consumed:
      - parcel_repo, user_repo, registry, detector, health, notifier (existing)
      - config (Phase 2): provides batch_size
      - rate_limiter (Phase 2): RateLimiter instance
      - prefs (Phase 2): NotificationPreferences instance for gating, OR None pre-item 19
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
    prefs = context.bot_data.get("prefs")  # None until item 19 wires NotificationPreferences
    geocoder = context.bot_data.get("geocoder")
    map_renderer = context.bot_data.get("map_renderer")
    now: Callable[[], datetime] = context.bot_data.get("now", _now_default)

    # Users whose parcels must be tracked: the allowed_users DB table PLUS the owner
    # and the env-configured allow-list. The owner is authorised via OWNER_ID and is
    # never inserted into allowed_users, so iterating the table alone skipped the
    # owner's parcels — the bot's primary user never received status updates.
    user_ids: set[int] = set(await user_repo.get_allowed_user_ids())
    owner_id = getattr(config, "owner_id", None)
    if owner_id is not None:
        user_ids.add(owner_id)
    user_ids.update(getattr(config, "allowed_user_ids", ()) or ())
    if not user_ids:
        return

    all_due: list[tuple[int, Parcel]] = []
    for user_id in user_ids:
        parcels = await parcel_repo.list_active_for_user(user_id=user_id)
        for parcel in parcels:
            if is_due(
                parcel.status,
                parcel.last_check_at,
                now(),
                delivery_disputed=parcel.delivery_disputed,
                delivered_at=parcel.delivered_at,
            ):
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
                    geocoder=geocoder,
                    map_renderer=map_renderer,
                    now=now,
                )
                for (uid, p) in batch
            ],
            return_exceptions=True,
        )


async def _persist_result(
    parcel_repo: ParcelRepository,
    tracking_number: str,
    result: TrackingResult,
) -> list[TrackingEvent]:
    """Persist new events (canonical store = tracking_history) and refresh the
    denormalised latest-event fields used by /status and notifications.

    Returns the events that were genuinely new (dedup-filtered), so the caller
    can decide whether a notification is warranted.
    """
    new_events = await parcel_repo.add_events_dedup(tracking_number, result.events)
    if result.last_event is not None:
        await parcel_repo.update_latest(
            tracking_number,
            result.last_event,
            result.last_event_time,
            result.last_location,
        )
    return new_events


async def _reconcile_status_and_carrier(
    parcel_repo: ParcelRepository,
    parcel: Parcel,
    result: TrackingResult,
) -> None:
    """Bring a successful result in line with the API-backed trackers.

    Scraper plugins (BRT/GLS Italy/SDA) return ``found=True`` with events but
    leave ``status`` at the NOT_FOUND default and never write the carrier back to
    the parcel row. This recovers a status from the latest event (mutating
    ``result`` so the caller's status-change detection sees it) and persists a
    carrier identified during the fetch, which ``create()`` would otherwise be
    the only writer of.
    """
    if result.status is ShipmentStatus.NOT_FOUND and result.last_event:
        derived = status_from_text(result.last_event)
        if derived is not None:
            result.status = derived

    if (result.carrier_code or result.carrier_name) and (
        result.carrier_code != parcel.carrier_code
        or result.carrier_name != parcel.carrier_name
    ):
        await parcel_repo.update_carrier(
            parcel.tracking_number,
            result.carrier_code or parcel.carrier_code,
            result.carrier_name or parcel.carrier_name,
        )


async def _handle_delivered_transition(
    *,
    parcel: Parcel,
    user_id: int,
    parcel_repo: ParcelRepository,
    notifier: TelegramNotifier,
    location: str | None,
    now: Callable[[], datetime],
) -> None:
    """On Delivered: stamp delivered_at and ask the user to confirm receipt (no auto-archive).

    The Yes/No confirmation prompt is a lifecycle action, not a routine notification:
    it is ALWAYS sent regardless of the user's DELIVERED notification preference, so a
    user who muted "Delivered" updates can still confirm/archive and the parcel does not
    linger active forever.
    """
    await parcel_repo.set_delivered(parcel.tracking_number, now())
    await notifier.send_delivery_confirmation(
        chat_id=user_id,
        tracking_number=parcel.tracking_number,
        parcel_name=parcel.name,
        location=location,
    )


async def _maybe_render_map(
    *,
    geocoder: Any | None,
    map_renderer: Any | None,
    history: list[TrackingEvent],
    new_events: list[TrackingEvent],
) -> bytes | None:
    """Best-effort: build a route from the geocodable event chain and render it.
    Never raises."""
    if geocoder is None or map_renderer is None or not history:
        return None
    from parcel_tracker.maps.route import build_route_waypoints  # noqa: PLC0415
    from parcel_tracker.maps.transport import infer_transport_mode  # noqa: PLC0415

    waypoints = build_route_waypoints(history, geocoder)
    if not waypoints:
        return None
    desc = new_events[-1].description if new_events else None
    carrier = new_events[-1].carrier if new_events else None
    mode = infer_transport_mode(carrier, desc)
    try:
        return await asyncio.to_thread(map_renderer.render_route, waypoints, mode=mode)
    except Exception:  # noqa: BLE001 — map is best-effort; never block the notification
        logger.warning("route map render failed", exc_info=True)
        return None


async def _notify(  # noqa: PLR0913
    *,
    parcel: Parcel,
    user_id: int,
    parcel_repo: ParcelRepository,
    notifier: TelegramNotifier,
    prefs: Any | None,
    final_result: TrackingResult,
    status_changed: bool,
    new_events: list[TrackingEvent],
    geocoder: Any | None = None,
    map_renderer: Any | None = None,
) -> None:
    """Render a per-event update message, gated by the user's status preference.

    No time cooldown: event dedup already prevents repeated notifications for the
    same events, so an explicit cooldown would only suppress legitimate updates.
    """
    enabled = prefs is None or await prefs.is_status_enabled(user_id, final_result.status)
    if not enabled:
        return
    ordered = sorted(new_events, key=lambda e: e.time or "")
    history = await parcel_repo.get_history(parcel.tracking_number, limit=50)
    history = sorted(history, key=lambda e: e.time or "")
    map_png = await _maybe_render_map(
        geocoder=geocoder,
        map_renderer=map_renderer,
        history=history,
        new_events=ordered,
    )
    await notifier.send_events_update(
        chat_id=user_id,
        tracking_number=parcel.tracking_number,
        parcel_name=parcel.name,
        carrier_name=final_result.carrier_name or parcel.carrier_name,
        old_status=parcel.status,
        new_status=final_result.status,
        status_changed=status_changed,
        new_events=ordered,
        location=final_result.last_location,
        map_png=map_png,
    )


async def _check_one(  # noqa: PLR0913, C901
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
    geocoder: Any | None = None,
    map_renderer: Any | None = None,
    notify_events: bool = True,
) -> str:
    """Check a single parcel: iterate matches in priority order until one succeeds.

    Phase 3 fallback semantics: when matches[0] fails (raises or returns
    found=False) or is quarantined, try matches[1], matches[2], ... until one
    returns found=True. Each tracker still records its own success/failure
    against its quarantine ladder; rate limit is acquired per tracker per call.

    Returns one of: "updated" | "no_change" | "failed" | "quarantined" |
    "no_tracker" | "delivered".

    Batch callers (asyncio.gather) ignore the return value — backward compatible.
    """
    matches = detector.detect(parcel.tracking_number)
    if not matches:
        logger.debug("No tracker matches for %s", parcel.tracking_number)
        return "no_tracker"

    final_result: TrackingResult | None = None
    attempted = False

    for tracker in matches:
        if await health.is_quarantined(tracker.name, parcel.tracking_number):
            logger.debug(
                "Skipping %s/%s — quarantined",
                tracker.name,
                parcel.tracking_number,
            )
            QUARANTINE_ACTIVE.labels(tracker=tracker.name).set(1)
            CHECK_TOTAL.labels(tracker=tracker.name, outcome="quarantined").inc()
            continue

        attempted = True
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
            continue

        if not result.found:
            CHECK_TOTAL.labels(tracker=tracker.name, outcome="failure").inc()
            await health.record_failure(tracker.name, parcel.tracking_number)
            continue

        CHECK_TOTAL.labels(tracker=tracker.name, outcome="success").inc()
        await health.record_success(tracker.name, parcel.tracking_number)
        final_result = result
        break

    await parcel_repo.set_last_check_at(parcel.tracking_number, now())

    if final_result is None:
        return "failed" if attempted else "quarantined"

    await _reconcile_status_and_carrier(parcel_repo, parcel, final_result)

    new_events = await _persist_result(parcel_repo, parcel.tracking_number, final_result)

    status_changed = final_result.status != parcel.status
    if status_changed:
        await parcel_repo.update_status(parcel.tracking_number, final_result.status)

    # Delivered transition: hand off to the confirmation flow (real impl added later).
    if status_changed and final_result.status is ShipmentStatus.DELIVERED:
        await _handle_delivered_transition(
            parcel=parcel,
            user_id=user_id,
            parcel_repo=parcel_repo,
            notifier=notifier,
            location=final_result.last_location,
            now=now,
        )
        return "delivered"

    # Notify on new events OR a coarse status change (no time cooldown — event
    # dedup already prevents duplicate notifications for the same events).
    if not (new_events or status_changed):
        return "no_change"
    if notify_events:
        await _notify(
            parcel=parcel,
            user_id=user_id,
            parcel_repo=parcel_repo,
            notifier=notifier,
            prefs=prefs,
            final_result=final_result,
            status_changed=status_changed,
            new_events=new_events,
            geocoder=geocoder,
            map_renderer=map_renderer,
        )
    return "updated"


async def check_parcel_now(
    bot_data: dict[str, Any], *, user_id: int, tracking_number: str
) -> str | None:
    """On-demand check of a SINGLE parcel (manual refresh from the detail card).

    Ownership-scoped: returns None when the parcel does not belong to the user.
    Event notifications are suppressed (the user is looking at the card); the
    delivered-confirmation lifecycle prompt is still sent.
    """
    parcel_repo: ParcelRepository = bot_data["parcel_repo"]
    parcel = await parcel_repo.get_for_user(tracking_number, user_id=user_id)
    if parcel is None:
        return None
    return await _check_one(
        parcel=parcel,
        user_id=user_id,
        parcel_repo=parcel_repo,
        detector=bot_data["detector"],
        health=bot_data["health"],
        notifier=bot_data["notifier"],
        rate_limiter=bot_data["rate_limiter"],
        prefs=bot_data.get("prefs"),
        geocoder=bot_data.get("geocoder"),
        map_renderer=bot_data.get("map_renderer"),
        now=bot_data.get("now", _now_default),
        notify_events=False,
    )
