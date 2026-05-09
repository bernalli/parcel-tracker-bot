# Architecture

A 10 000-foot view of how `parcel-tracker-bot` is structured. For implementation details, read
the source — every module has a top-of-file docstring summarising its responsibility.

## Layered design

```
┌─────────────────────────────────────────────────────────────────┐
│ bot/                                                            │
│   handlers.py · auth_commands.py · parcel_commands.py · …       │
│   (Telegram-facing layer; delegates to repositories + scheduler)│
└──────────────────────────────┬──────────────────────────────────┘
                               │
                  ┌────────────┴────────────┐
                  │                         │
        ┌─────────▼────────┐      ┌─────────▼───────────┐
        │ core/scheduler.py│      │ db/repository.py    │
        │ + retry_policy   │      │ db/health_repo      │
        │ + rate_limiter   │      │ db/notification_repo│
        └─────────┬────────┘      └─────────────────────┘
                  │
       ┌──────────▼───────────────────────────┐
       │ core/registry.py · core/detector.py  │
       │   (resolves a tracking_id → Tracker) │
       └──────────┬───────────────────────────┘
                  │
       ┌──────────▼───────────────────────────┐
       │ trackers/<name>.py                   │
       │   AbstractTracker subclasses         │
       │   (one per courier, plugin-friendly) │
       └──────────────────────────────────────┘
```

## Core concepts

### `AbstractTracker`

The plugin contract. A courier implementation declares:
- `name: str` — human-readable identifier (e.g., `"DHL"`)
- `priority: int` — higher wins when several trackers match the same ID
- `tracking_id_patterns: list[re.Pattern]` — regex matches for auto-detection
- `country_codes: list[str]` — informational, used by the future detection UI
- `async def fetch(tracking_id: str) -> TrackingResult` — the only mandatory method

### `TrackerRegistry`

Loads built-in trackers (entry points + dir scan of `src/parcel_tracker/trackers/`) and
external plugins (drop-in `plugins/` dir, path overridable via `PARCEL_TRACKER_PLUGIN_DIR`).

### `CourierDetector`

Given a tracking ID, it iterates registered trackers ordered by `priority` desc and returns
the first regex hit. Ties broken by registration order. Used by `/add` so the user does not
need to specify a carrier.

### `HealthManager` (Phase 1, F1.5)

Tracks per-tracker success/failure ratios, records consecutive failures, and quarantines a
tracker for `1h / 6h / 24h` after `3 / 6 / 12` consecutive failures. Decorated calls auto-skip
quarantined trackers.

### `Scheduler` (Phase 2, F2)

Runs every `STATUS_INTERVAL_*` minutes (per shipment status) in a single periodic Telegram job.
Each tick:
1. Pulls candidate parcels (`is_due()`).
2. Runs them in parallel batches of `BATCH_SIZE` (default 10).
3. Applies the per-tracker `RateLimiter` (token bucket).
4. Calls each tracker via `@health_aware` decorator.
5. Persists new events, updates statuses, sends Telegram notifications gated by user prefs +
   cooldown.

### `Notifier` + `NotificationPreferences` (Phase 2, F4)

Per-user, per-status preferences with a default-on set: `delivered`, `exception`,
`out_for_delivery`, `returned`. Cooldown of `NOTIFY_COOLDOWN_MINUTES` (default 60) per
`(parcel, event_type)` to avoid spam.

### `Observability` (Phase 2, F1)

- `structlog` configured at startup; output is JSON in production, console in dev (`LOG_FORMAT`).
- `prometheus-client` exposes 8 metrics on `:9090/metrics` (`METRICS_BIND_HOST`,
  `METRICS_PORT`).

## Data flow — `/add <tracking_id>` to first notification

```
User → Telegram → bot/parcel_commands.cmd_add
                  │
                  ├─ ParcelRepository.add()      (writes parcels row)
                  └─ schedules immediate check via _check_one()
                                          │
                                          ├─ CourierDetector.match()
                                          ├─ Scheduler runs Tracker.fetch()
                                          │   (with retry, rate-limit, health-aware)
                                          ├─ ParcelRepository.update_status()
                                          ├─ HealthRepository.record_success/failure()
                                          └─ TelegramNotifier.send_if_allowed()
                                                          │
                                                          └─ Telegram → User
```

## Persistence

SQLite via `aiosqlite`. WAL mode enabled. Schema lives in `src/parcel_tracker/db/migrations.py`
as a list of idempotent statements; each new schema change appends a statement guarded by
`IF NOT EXISTS`. No alembic in v0.1.x — too heavyweight for a single SQLite file.

Tables: `users`, `parcels`, `tracking_events`, `tracker_health`,
`user_notification_prefs`, `notification_cooldown_log`.

## Plugin discovery — built-in vs drop-in

- **Built-in**: every `*.py` under `src/parcel_tracker/trackers/` whose top-level class
  inherits `AbstractTracker` is registered at import time.
- **Drop-in**: every `*.py` under `plugins/` (or `$PARCEL_TRACKER_PLUGIN_DIR`) is imported
  at startup. Subdirectories are walked. The production deploy uses `plugins/it/` for the four
  Italian couriers (BRT, GLS Italy, SDA, Poste Italiane) which are not part of the public
  repo.

## What is intentionally *not* here

- No SaaS / multi-tenant features. One bot, one owner, an allowlist of users.
- No web dashboard. Telegram is the only UI.
- No PostgreSQL/MySQL adapter. SQLite is enough; we will reconsider if we ever hit limits.
- No webhook mode for Telegram. Long polling is simpler and works behind NAT.
- No PyPI package. The supported install path is `git clone` + Docker.
