# Observability

Two production-grade signals are emitted out of the box: structured JSON logs and
Prometheus metrics.

## Structured logging

The bot uses [`structlog`](https://www.structlog.org/) configured at startup. The format is
controlled by `LOG_FORMAT`:

- `LOG_FORMAT=json` (default) — one JSON object per line, ready for Loki/Elasticsearch.
- `LOG_FORMAT=console` — coloured human-readable, useful in `docker compose logs -f`.

Every log line includes:

- `timestamp` (ISO 8601, UTC)
- `level` (`info`, `warning`, `error`, …)
- `logger` (`parcel_tracker.scheduler`, `parcel_tracker.bot.handlers`, …)
- `event` (a short snake_case verb, e.g., `tracker_check_success`, `notification_sent`)
- `tracker_id`, `tracking_id`, `latency_ms`, `error_class` (when applicable)

`tracking_id` is **hashed** (SHA-256, first 8 hex chars) by default to keep PII out of logs.
Set `LOG_FULL_TRACKING_ID=true` if you are debugging locally and want the raw value back.

## Prometheus metrics

The bot starts an HTTP exporter on `METRICS_BIND_HOST:METRICS_PORT` (default `0.0.0.0:9090`).
Disable with `METRICS_ENABLED=false`. Eight metrics are exposed:

| Metric                                              | Type      | Labels         |
|-----------------------------------------------------|-----------|----------------|
| `parceltracker_check_total`                         | counter   | `tracker`, `outcome` |
| `parceltracker_check_latency_seconds`               | histogram | `tracker`            |
| `parceltracker_quarantine_active`                   | gauge     | `tracker`            |
| `parceltracker_telegram_sent_total`                 | counter   | `event_type`         |
| `parceltracker_telegram_errors_total`               | counter   | `error_class`        |
| `parceltracker_db_query_duration_seconds`           | histogram | `op`                 |
| `parceltracker_scheduler_tick_duration_seconds`     | histogram | (none)               |
| `parceltracker_active_shipments`                    | gauge     | (none)               |

`outcome ∈ {success, failure, quarantined, retry_exhausted}`.

## Wiring Prometheus

Add a scrape target:

```yaml
scrape_configs:
  - job_name: parcel-tracker
    metrics_path: /metrics
    static_configs:
      - targets: ['parcel-tracker-bot:9090']
        labels:
          deployment: home
```

If you expose `:9090` outside the Docker network, **gate it** behind your reverse proxy with
basic auth or restrict the firewall to your monitoring host. There is no auth on the metrics
endpoint by design (Prometheus scrapers do not authenticate).

## Grafana

A pre-built dashboard ships at `docs/grafana/parcel-tracker-dashboard.json`. Import it in
Grafana via **Dashboards → New → Import → Upload JSON file**.

Panels:

- Tracker check rate (success vs failure)
- Tracker latency p50/p95/p99 by carrier
- Active quarantines
- Telegram notification volume
- Scheduler tick duration
- DB query latency

## Alerting (optional)

A reasonable starter set in PromQL:

```promql
# Tracker quarantined for >24h
parceltracker_quarantine_active == 1
  AND on() time() - (parceltracker_quarantine_active offset 24h) > 0

# Telegram error rate above 5/min
rate(parceltracker_telegram_errors_total[5m]) > 5/60

# Scheduler tick taking >30s
histogram_quantile(0.95, rate(parceltracker_scheduler_tick_duration_seconds_bucket[5m])) > 30
```

## Disabling observability

If you are running on a constrained device and want neither Prometheus nor JSON logs:

```
LOG_FORMAT=console
METRICS_ENABLED=false
```

The metrics HTTP server simply does not start.
