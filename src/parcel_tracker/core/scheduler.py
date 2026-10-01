"""Periodic tracking job — checks active parcels with dynamic interval, parallel batch,
and per-tracker rate limiting."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from typing import Any, Protocol

from parcel_tracker.core.detector import CourierDetector
from parcel_tracker.core.event_status import status_from_text
from parcel_tracker.core.health import HealthManager
from parcel_tracker.core.rate_limiter import RateLimiter
from parcel_tracker.core.status_intervals import get_interval_minutes, is_due
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


class _KeyedLock:
    """A lock plus the number of tasks holding or waiting on it."""

    __slots__ = ("lock", "users")

    def __init__(self) -> None:
        self.lock = asyncio.Lock()
        self.users = 0


_CHECK_LOCKS: dict[tuple[int, str], _KeyedLock] = {}


@asynccontextmanager
async def _parcel_check_lock(user_id: int, tracking_number: str) -> AsyncIterator[bool]:
    """Hold the per-(user, parcel) check lock; yields True if it had to wait.

    Entries are dropped when the last holder or waiter leaves, so the registry only
    ever contains parcels being checked right now.
    """
    key = (user_id, tracking_number)
    entry = _CHECK_LOCKS.setdefault(key, _KeyedLock())
    entry.users += 1
    waited = entry.lock.locked()
    try:
        async with entry.lock:
            yield waited
    finally:
        entry.users -= 1
        if entry.users == 0:
            _CHECK_LOCKS.pop(key, None)


def _now_default() -> datetime:
    return datetime.now(UTC)


def _chunked(seq: list[tuple[int, Parcel]], size: int) -> list[list[tuple[int, Parcel]]]:
    return [seq[i : i + size] for i in range(0, len(seq), size)]


def _log_batch_errors(batch: list[tuple[int, Parcel]], results: list[Any]) -> None:
    """Surface exceptions returned by ``asyncio.gather(return_exceptions=True)``.

    Without this a per-parcel failure (including a notification that passed the
    gate but failed to send) is silently discarded — no log, no retry — so the
    user just never hears about an update. Log, don't raise: one bad parcel must
    not abort the rest of the batch.
    """
    for (uid, parcel), res in zip(batch, results, strict=False):
        if isinstance(res, Exception):
            logger.warning(
                "parcel check task failed (user=%s, tracking=%s): %s",
                uid,
                parcel.tracking_number,
                res,
                exc_info=res,
            )


async def check_user_now(bot_data: dict[str, Any], *, user_id: int) -> int:
    """On-demand: check ALL active parcels for a user immediately (ignores is_due).
    Returns the number of parcels checked. Reuses _check_one."""
    parcel_repo: ParcelRepository = bot_data["parcel_repo"]
    parcels = await parcel_repo.list_active_for_user(user_id=user_id)
    if not parcels:
        return 0
    batch_size = int(getattr(bot_data["config"], "batch_size", 10))
    for batch in _chunked([(user_id, p) for p in parcels], batch_size):
        results = await asyncio.gather(
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
        _log_batch_errors(batch, results)
    return len(parcels)


async def reconcile_delivered_backlog(bot_data: dict[str, Any]) -> int:
    """One-shot startup pass: heal DELIVERED parcels that never went through the
    delivery-confirmation lifecycle (``delivered_at IS NULL``) — stamp delivered_at
    and send a single confirm/archive prompt so they don't linger active forever.

    Returns the number of parcels reconciled. No-op (0) when bot_data lacks the
    repo or notifier so the startup hook stays safe in minimal contexts.
    """
    parcel_repo: ParcelRepository | None = bot_data.get("parcel_repo")
    notifier: TelegramNotifier | None = bot_data.get("notifier")
    if parcel_repo is None or notifier is None:
        return 0
    now: Callable[[], datetime] = bot_data.get("now", _now_default)
    parcels = await parcel_repo.list_active_delivered_unstamped()
    healed = 0
    for parcel in parcels:
        try:
            await notifier.send_delivery_confirmation(
                chat_id=parcel.user_id,
                tracking_number=parcel.tracking_number,
                parcel_name=parcel.name,
                location=parcel.last_location,
            )
        except Exception:  # noqa: BLE001 — one bad send must not abort the sweep
            # Leave delivered_at unset so the next startup retries this parcel; a
            # stamped-but-silent parcel would never surface the confirm prompt again.
            logger.warning(
                "startup delivered-backlog confirmation failed for %s (will retry next start)",
                parcel.tracking_number,
                exc_info=True,
            )
            continue
        await parcel_repo.set_delivered(parcel.tracking_number, now(), user_id=parcel.user_id)
        # The prompt supersedes the per-event update (as in the live transition), so
        # consume the pending events; otherwise a later poll would re-prompt for them.
        unnotified = await parcel_repo.get_unnotified(
            parcel.tracking_number, user_id=parcel.user_id
        )
        await parcel_repo.mark_notified([row_id for row_id, _ev in unnotified])
        healed += 1
    return healed


async def _sweep_delivered_backlog(bot_data: dict[str, Any]) -> None:
    """Per-tick reconcile_delivered_backlog; a failure here must never block polling."""
    try:
        await reconcile_delivered_backlog(bot_data)
    except Exception:  # noqa: BLE001 — logged and retried next tick
        logger.warning("delivered-backlog sweep failed", exc_info=True)


def _is_stalled(parcel: Parcel, overrides: Any) -> bool:
    """True for a parcel polling will never select again (zero interval).

    An unstamped DELIVERED parcel is excluded: reconcile_delivered_backlog owns it.
    """
    if parcel.status is ShipmentStatus.DELIVERED and parcel.delivered_at is None:
        return False
    return get_interval_minutes(parcel.status, overrides) == 0


async def _flush_stalled_notifications(  # noqa: PLR0913
    *,
    stalled: list[tuple[int, Parcel]],
    parcel_repo: ParcelRepository,
    notifier: TelegramNotifier,
    prefs: Any | None,
    geocoder: Any | None,
    map_renderer: Any | None,
) -> None:
    """Retry notifications for parcels that dropped out of the polling set.

    Terminal statuses (DELIVERED, EXPIRED) have a zero polling interval, so a send
    that failed on the cycle that reached them would never be retried by polling.
    Events stay ``notified = 0`` until a send succeeds, which makes them the outbox:
    each tick re-sends whatever is still pending for these parcels. A DELIVERED
    parcel gets the confirm/archive prompt, anything else the regular update.
    """
    for user_id, parcel in stalled:
        try:
            unnotified = await parcel_repo.get_unnotified(parcel.tracking_number, user_id=user_id)
            if not unnotified:
                continue
            if parcel.status is ShipmentStatus.DELIVERED:
                await notifier.send_delivery_confirmation(
                    chat_id=user_id,
                    tracking_number=parcel.tracking_number,
                    parcel_name=parcel.name,
                    location=parcel.last_location,
                )
                await parcel_repo.mark_notified([row_id for row_id, _ev in unnotified])
            else:
                # _notify marks each batch notified as its message goes out.
                await _notify(
                    parcel=parcel,
                    user_id=user_id,
                    parcel_repo=parcel_repo,
                    notifier=notifier,
                    prefs=prefs,
                    final_result=TrackingResult(
                        tracking_number=parcel.tracking_number,
                        found=True,
                        status=parcel.status,
                        carrier_name=parcel.carrier_name,
                        last_location=parcel.last_location,
                    ),
                    status_changed=False,
                    unnotified=unnotified,
                    geocoder=geocoder,
                    map_renderer=map_renderer,
                )
        except Exception:  # noqa: BLE001 — one bad send must not abort the sweep
            logger.warning(
                "pending notification retry failed for %s (will retry next tick)",
                parcel.tracking_number,
                exc_info=True,
            )


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
      - prefs: NotificationPreferences instance for gating, or None
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
    prefs = context.bot_data.get("prefs")  # None until NotificationPreferences is wired in
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

    # A delivery prompt that failed to send leaves delivered_at unset; retry it on
    # every tick instead of only at startup.
    await _sweep_delivered_backlog(context.bot_data)

    overrides = getattr(config, "status_interval_overrides", None)
    all_due: list[tuple[int, Parcel]] = []
    stalled: list[tuple[int, Parcel]] = []
    for user_id in user_ids:
        parcels = await parcel_repo.list_active_for_user(user_id=user_id)
        for parcel in parcels:
            if is_due(
                parcel.status,
                parcel.last_check_at,
                now(),
                delivery_disputed=parcel.delivery_disputed,
                delivered_at=parcel.delivered_at,
                interval_overrides=overrides,
            ):
                all_due.append((user_id, parcel))
            elif _is_stalled(parcel, overrides):
                stalled.append((user_id, parcel))

    await _flush_stalled_notifications(
        stalled=stalled,
        parcel_repo=parcel_repo,
        notifier=notifier,
        prefs=prefs,
        geocoder=geocoder,
        map_renderer=map_renderer,
    )

    if not all_due:
        return

    rank = {status: idx for idx, status in enumerate(PRIORITY_ORDER)}
    all_due.sort(key=lambda pair: rank.get(pair[1].status, 999))

    batch_size = int(getattr(config, "batch_size", 10))
    for batch in _chunked(all_due, batch_size):
        results = await asyncio.gather(
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
        _log_batch_errors(batch, results)


async def _persist_result(
    parcel_repo: ParcelRepository,
    tracking_number: str,
    result: TrackingResult,
    *,
    user_id: int,
) -> list[TrackingEvent]:
    """Persist new events (canonical store = tracking_history) and refresh the
    denormalised latest-event fields used by /status and notifications.

    Returns the events that were genuinely new (dedup-filtered), so the caller
    can decide whether a notification is warranted.
    """
    new_events = await parcel_repo.add_events_dedup(tracking_number, result.events, user_id=user_id)
    if result.last_event is not None:
        await parcel_repo.update_latest(
            tracking_number,
            result.last_event,
            result.last_event_time,
            result.last_location,
            user_id=user_id,
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
    if result.status is ShipmentStatus.NOT_FOUND:
        if result.last_event:
            derived = status_from_text(result.last_event)
            if derived is not None:
                result.status = derived
        elif result.events:
            # Events present but no denormalised ``last_event``: ordering is
            # tracker-specific so we can't safely pick the newest, but a result
            # carrying movement events is never "unknown" — it is at least in
            # transit. Lifting NOT_FOUND here stops the ``is_status_enabled``
            # gate (which hard-suppresses the internal NOT_FOUND state) from
            # silently swallowing genuine intermediate updates.
            result.status = ShipmentStatus.IN_TRANSIT

    if (result.carrier_code or result.carrier_name) and (
        result.carrier_code != parcel.carrier_code or result.carrier_name != parcel.carrier_name
    ):
        await parcel_repo.update_carrier(
            parcel.tracking_number,
            result.carrier_code or parcel.carrier_code,
            result.carrier_name or parcel.carrier_name,
            user_id=parcel.user_id,
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
    # Send first: if it raises, delivered_at stays unset and the per-tick
    # reconcile_delivered_backlog sweep retries the prompt.
    await notifier.send_delivery_confirmation(
        chat_id=user_id,
        tracking_number=parcel.tracking_number,
        parcel_name=parcel.name,
        location=location,
    )
    await parcel_repo.set_delivered(parcel.tracking_number, now(), user_id=user_id)


async def _reprompt_delivered(  # noqa: PLR0913
    *,
    parcel: Parcel,
    user_id: int,
    parcel_repo: ParcelRepository,
    notifier: TelegramNotifier,
    location: str | None,
    unnotified_ids: list[int],
    now: Callable[[], datetime],
) -> None:
    """Re-send the confirm/archive prompt for an already Delivered parcel."""
    await notifier.send_delivery_confirmation(
        chat_id=user_id,
        tracking_number=parcel.tracking_number,
        parcel_name=parcel.name,
        location=location,
    )
    if parcel.delivered_at is None:
        # A transition whose prompt failed earlier: stamp it now so the per-tick
        # backlog sweep does not prompt a second time.
        await parcel_repo.set_delivered(parcel.tracking_number, now(), user_id=user_id)
    await parcel_repo.mark_notified(unnotified_ids)


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
    unnotified: list[tuple[int, TrackingEvent]],
    geocoder: Any | None = None,
    map_renderer: Any | None = None,
) -> None:
    """Render a per-event update message, gated by the user's status preference,
    and mark the events notified as each message goes out.

    No time cooldown: event dedup already prevents repeated notifications for the
    same events, so an explicit cooldown would only suppress legitimate updates.
    """
    event_ids = {id(ev): row_id for row_id, ev in unnotified}
    new_events = [ev for _id, ev in unnotified]
    enabled = prefs is None or await prefs.is_status_enabled(user_id, final_result.status)
    if not enabled:
        await parcel_repo.mark_notified(list(event_ids.values()))
        return
    from parcel_tracker.maps.route import order_events  # noqa: PLC0415

    async def _mark_sent(sent: list[TrackingEvent]) -> None:
        await parcel_repo.mark_notified([event_ids[id(ev)] for ev in sent])

    ordered = order_events(new_events)
    history = await parcel_repo.get_history(parcel.tracking_number, limit=50, user_id=user_id)
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
        on_events_sent=_mark_sent,
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
    geocoder: Any | None = None,
    map_renderer: Any | None = None,
    notify_events: bool = True,
) -> str:
    """Serialise checks of one (user, parcel) across every entrypoint.

    The periodic poll, /checkall and the manual refresh all land here. Without the
    lock two concurrent runs read the same stale status and the same unnotified
    events, and the user gets the update (or the delivery prompt) twice. A run that
    had to wait re-reads the parcel, so it compares against what the first run wrote.
    """
    async with _parcel_check_lock(user_id, parcel.tracking_number) as waited:
        if waited:
            fresh = await parcel_repo.get_for_user(parcel.tracking_number, user_id=user_id)
            if fresh is None or not fresh.is_active:
                return "no_change"
            parcel = fresh
        return await _check_one_unlocked(
            parcel=parcel,
            user_id=user_id,
            parcel_repo=parcel_repo,
            detector=detector,
            health=health,
            notifier=notifier,
            rate_limiter=rate_limiter,
            prefs=prefs,
            now=now,
            geocoder=geocoder,
            map_renderer=map_renderer,
            notify_events=notify_events,
        )


async def _check_one_unlocked(  # noqa: PLR0913, C901
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

    Fallback semantics: when matches[0] fails (raises or returns
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

    await parcel_repo.set_last_check_at(parcel.tracking_number, now(), user_id=user_id)

    if final_result is None:
        return "failed" if attempted else "quarantined"

    await _reconcile_status_and_carrier(parcel_repo, parcel, final_result)

    await _persist_result(parcel_repo, parcel.tracking_number, final_result, user_id=user_id)

    status_changed = final_result.status != parcel.status
    if status_changed:
        await parcel_repo.update_status(
            parcel.tracking_number, final_result.status, user_id=user_id
        )

    # Drive notification off persisted-but-unnotified events: events are
    # committed before the send, so if _notify raises (Telegram timeout/429) they
    # must stay notified=0 and be retried next cycle instead of being lost forever.
    unnotified = await parcel_repo.get_unnotified(parcel.tracking_number, user_id=user_id)
    unnotified_ids = [row_id for row_id, _ev in unnotified]

    # Delivered transition: the confirmation prompt supersedes a per-event update,
    # so consume the pending events (mark notified) without sending one.
    if status_changed and final_result.status is ShipmentStatus.DELIVERED:
        await _handle_delivered_transition(
            parcel=parcel,
            user_id=user_id,
            parcel_repo=parcel_repo,
            notifier=notifier,
            location=final_result.last_location,
            now=now,
        )
        await parcel_repo.mark_notified(unnotified_ids)
        return "delivered"

    # Re-prompt: a parcel already Delivered that gets genuinely new events re-sends
    # the confirm/archive prompt (a lifecycle action, like the first transition) so
    # one the user never confirmed doesn't linger silently. The notified-flag dedup
    # is the per-parcel cooldown — idle polls (no new events) never re-prompt.
    if final_result.status is ShipmentStatus.DELIVERED and unnotified_ids:
        await _reprompt_delivered(
            parcel=parcel,
            user_id=user_id,
            parcel_repo=parcel_repo,
            notifier=notifier,
            location=final_result.last_location,
            unnotified_ids=unnotified_ids,
            now=now,
        )
        return "delivered"

    if not (unnotified or status_changed):
        return "no_change"
    if notify_events:
        # _notify marks each batch of events as its message goes out (or all of them
        # when prefs suppress the update); events of a failed send stay unnotified
        # and are retried next cycle.
        await _notify(
            parcel=parcel,
            user_id=user_id,
            parcel_repo=parcel_repo,
            notifier=notifier,
            prefs=prefs,
            final_result=final_result,
            status_changed=status_changed,
            unnotified=unnotified,
            geocoder=geocoder,
            map_renderer=map_renderer,
        )
    else:
        await parcel_repo.mark_notified(unnotified_ids)
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
