"""Tests for Prometheus collectors: existence, label cardinality, output format."""

from __future__ import annotations

from prometheus_client import CollectorRegistry, generate_latest

from parcel_tracker.observability.metrics import (
    ACTIVE_PARCELS,
    CHECK_LATENCY_SECONDS,
    CHECK_TOTAL,
    DB_QUERY_DURATION_SECONDS,
    QUARANTINE_ACTIVE,
    SCHEDULER_TICK_DURATION_SECONDS,
    TELEGRAM_ERRORS_TOTAL,
    TELEGRAM_SENT_TOTAL,
    build_registry,
)


def test_check_total_increments_with_labels() -> None:
    CHECK_TOTAL.labels(tracker="dhl", outcome="success").inc()
    metric = CHECK_TOTAL.labels(tracker="dhl", outcome="success")
    assert metric._value.get() >= 1.0


def test_check_latency_histogram_observes_value() -> None:
    CHECK_LATENCY_SECONDS.labels(tracker="track17").observe(0.5)
    samples = list(CHECK_LATENCY_SECONDS.collect()[0].samples)
    sums = [s for s in samples if s.name.endswith("_sum")]
    assert any(s.value >= 0.5 for s in sums if s.labels.get("tracker") == "track17")


def test_quarantine_active_gauge_set() -> None:
    QUARANTINE_ACTIVE.labels(tracker="dhl").set(1)
    assert QUARANTINE_ACTIVE.labels(tracker="dhl")._value.get() == 1.0
    QUARANTINE_ACTIVE.labels(tracker="dhl").set(0)
    assert QUARANTINE_ACTIVE.labels(tracker="dhl")._value.get() == 0.0


def test_telegram_sent_total_counter() -> None:
    before = TELEGRAM_SENT_TOTAL.labels(status_value="Delivered")._value.get()
    TELEGRAM_SENT_TOTAL.labels(status_value="Delivered").inc()
    after = TELEGRAM_SENT_TOTAL.labels(status_value="Delivered")._value.get()
    assert after == before + 1.0


def test_telegram_errors_total_counter() -> None:
    before = TELEGRAM_ERRORS_TOTAL.labels(error_class="TelegramError")._value.get()
    TELEGRAM_ERRORS_TOTAL.labels(error_class="TelegramError").inc()
    after = TELEGRAM_ERRORS_TOTAL.labels(error_class="TelegramError")._value.get()
    assert after == before + 1.0


def test_db_query_duration_histogram() -> None:
    DB_QUERY_DURATION_SECONDS.labels(op="select").observe(0.005)
    samples = list(DB_QUERY_DURATION_SECONDS.collect()[0].samples)
    counts = [s for s in samples if s.name.endswith("_count") and s.labels.get("op") == "select"]
    assert any(s.value >= 1.0 for s in counts)


def test_scheduler_tick_histogram() -> None:
    SCHEDULER_TICK_DURATION_SECONDS.observe(2.5)
    samples = list(SCHEDULER_TICK_DURATION_SECONDS.collect()[0].samples)
    sums = [s for s in samples if s.name.endswith("_sum")]
    assert any(s.value >= 2.5 for s in sums)


def test_active_parcels_gauge_set() -> None:
    ACTIVE_PARCELS.set(42)
    assert ACTIVE_PARCELS._value.get() == 42.0


def test_build_registry_returns_collector_registry() -> None:
    registry = build_registry()
    assert isinstance(registry, CollectorRegistry)
    output = generate_latest(registry).decode("utf-8")
    assert "parceltracker_check_total" in output
    assert "parceltracker_check_latency_seconds" in output
    assert "parceltracker_quarantine_active" in output
    assert "parceltracker_telegram_sent_total" in output
    assert "parceltracker_telegram_errors_total" in output
    assert "parceltracker_db_query_duration_seconds" in output
    assert "parceltracker_scheduler_tick_duration_seconds" in output
    assert "parceltracker_active_parcels" in output
