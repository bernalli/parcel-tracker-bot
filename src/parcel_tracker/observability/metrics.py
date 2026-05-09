"""Prometheus collectors: counters, histograms, gauges for parcel-tracker.

All metrics live on the default global registry (prometheus_client.REGISTRY) so
that prometheus_client.start_http_server() exposes them automatically.
"""

from __future__ import annotations

from prometheus_client import REGISTRY, CollectorRegistry, Counter, Gauge, Histogram

CHECK_TOTAL = Counter(
    "parceltracker_check_total",
    "Total tracker checks performed by outcome",
    labelnames=["tracker", "outcome"],
)

CHECK_LATENCY_SECONDS = Histogram(
    "parceltracker_check_latency_seconds",
    "Latency of tracker fetch calls",
    labelnames=["tracker"],
    buckets=(0.1, 0.5, 1.0, 2.0, 5.0, 10.0, 30.0),
)

QUARANTINE_ACTIVE = Gauge(
    "parceltracker_quarantine_active",
    "1 if tracker is currently quarantined, 0 otherwise",
    labelnames=["tracker"],
)

TELEGRAM_SENT_TOTAL = Counter(
    "parceltracker_telegram_sent_total",
    "Telegram notifications successfully sent by status_value",
    labelnames=["status_value"],
)

TELEGRAM_ERRORS_TOTAL = Counter(
    "parceltracker_telegram_errors_total",
    "Telegram send errors by error class",
    labelnames=["error_class"],
)

DB_QUERY_DURATION_SECONDS = Histogram(
    "parceltracker_db_query_duration_seconds",
    "Database query duration by operation",
    labelnames=["op"],
    buckets=(0.001, 0.01, 0.05, 0.1, 0.5, 1.0),
)

SCHEDULER_TICK_DURATION_SECONDS = Histogram(
    "parceltracker_scheduler_tick_duration_seconds",
    "Duration of one scheduler tick (full pass over active parcels)",
    buckets=(0.5, 1.0, 5.0, 10.0, 30.0, 60.0, 120.0, 300.0),
)

ACTIVE_PARCELS = Gauge(
    "parceltracker_active_parcels",
    "Active parcels count (excludes Delivered/Expired)",
)


def build_registry() -> CollectorRegistry:
    """Return the default Prometheus registry where collectors are registered.

    Useful for tests and for callers that want to call generate_latest() directly.
    """
    return REGISTRY
