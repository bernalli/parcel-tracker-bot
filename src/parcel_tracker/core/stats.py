"""Shipment statistics for the dashboard and the bot (pure functions, no I/O)."""

from __future__ import annotations

import statistics
from collections import Counter
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta

from parcel_tracker.core.shipments import (
    FINAL_STATUSES,
    StatusGroup,
    is_stalled,
    needs_attention,
    status_group,
)
from parcel_tracker.db.models import Parcel, ShipmentStatus

RECENT_DAYS = 30
WEEKS = 12
_SECONDS_PER_DAY = 86400.0


@dataclass(frozen=True, slots=True)
class CarrierStats:
    carrier: str
    total: int
    delivered: int
    issues: int
    median_days: float | None


@dataclass(frozen=True, slots=True)
class WeekBucket:
    week_start: date
    shipped: int
    delivered: int


@dataclass(slots=True)
class ShipmentStats:
    total: int = 0
    active: int = 0
    by_group: dict[StatusGroup, int] = field(default_factory=dict)
    attention: int = 0
    stalled: int = 0
    shipped_recent: int = 0
    delivered_recent: int = 0
    median_delivery_days: float | None = None
    p90_delivery_days: float | None = None
    delivery_rate: float | None = None
    weekly: list[WeekBucket] = field(default_factory=list)
    carriers: list[CarrierStats] = field(default_factory=list)


def delivery_days(parcel: Parcel) -> float | None:
    """Days from when the shipment was added to delivery (None if unknown/negative)."""
    if parcel.delivered_at is None or parcel.created_at is None:
        return None
    seconds = (parcel.delivered_at - parcel.created_at).total_seconds()
    return seconds / _SECONDS_PER_DAY if seconds >= 0 else None


def _week_start(day: date) -> date:
    return day - timedelta(days=day.weekday())


def _percentile(values: list[float], pct: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, round(pct * (len(ordered) - 1))))
    return ordered[index]


def delivery_outcome(parcel: Parcel) -> bool | None:
    """True if delivered, False if it failed for good, None while still undecided.

    A failed attempt or an exception on an active parcel is not an outcome yet: the
    carrier often delivers the next day. It becomes one when the carrier returns
    the parcel or gives up, or when the seller archives it in that state.
    """
    if parcel.status is ShipmentStatus.DELIVERED:
        return True
    if status_group(parcel.status) is StatusGroup.ATTENTION and (
        parcel.status in FINAL_STATUSES or not parcel.is_active
    ):
        return False
    return None


def carrier_label(parcel: Parcel) -> str:
    return parcel.carrier_name or parcel.carrier_code or "?"


def _carrier_stats(parcels: list[Parcel]) -> list[CarrierStats]:
    groups: dict[str, list[Parcel]] = {}
    for parcel in parcels:
        groups.setdefault(carrier_label(parcel), []).append(parcel)
    rows: list[CarrierStats] = []
    for carrier, items in groups.items():
        days = [d for p in items if (d := delivery_days(p)) is not None]
        rows.append(
            CarrierStats(
                carrier=carrier,
                total=len(items),
                delivered=sum(1 for p in items if p.status is ShipmentStatus.DELIVERED),
                issues=sum(1 for p in items if status_group(p.status) is StatusGroup.ATTENTION),
                median_days=statistics.median(days) if days else None,
            )
        )
    rows.sort(key=lambda r: (-r.total, r.carrier))
    return rows


def _weekly(parcels: list[Parcel], today: date, weeks: int) -> list[WeekBucket]:
    first = _week_start(today) - timedelta(weeks=weeks - 1)
    shipped: Counter[date] = Counter()
    delivered: Counter[date] = Counter()
    for parcel in parcels:
        if parcel.created_at is not None:
            shipped[_week_start(parcel.created_at.date())] += 1
        if parcel.delivered_at is not None:
            delivered[_week_start(parcel.delivered_at.date())] += 1
    return [
        WeekBucket(week_start=w, shipped=shipped[w], delivered=delivered[w])
        for w in (first + timedelta(weeks=i) for i in range(weeks))
    ]


def compute_stats(
    parcels: Iterable[Parcel], *, now: datetime, stall_days: int, weeks: int = WEEKS
) -> ShipmentStats:
    items = list(parcels)
    stats = ShipmentStats(total=len(items))
    active = [p for p in items if p.is_active]
    stats.active = len(active)
    stats.by_group = dict(Counter(status_group(p.status) for p in active))
    stats.attention = sum(1 for p in active if needs_attention(p, now, stall_days))
    stats.stalled = sum(1 for p in active if is_stalled(p, now, stall_days))

    recent = now - timedelta(days=RECENT_DAYS)
    stats.shipped_recent = sum(1 for p in items if p.created_at and p.created_at >= recent)
    delivered_recent = [p for p in items if p.delivered_at and p.delivered_at >= recent]
    stats.delivered_recent = len(delivered_recent)

    days = [d for p in items if (d := delivery_days(p)) is not None]
    stats.median_delivery_days = statistics.median(days) if days else None
    stats.p90_delivery_days = _percentile(days, 0.9)

    outcomes = [o for p in items if (o := delivery_outcome(p)) is not None]
    if outcomes:
        stats.delivery_rate = sum(outcomes) / len(outcomes)

    stats.weekly = _weekly(items, now.date(), weeks)
    stats.carriers = _carrier_stats(items)
    return stats
