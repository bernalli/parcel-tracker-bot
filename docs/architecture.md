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
        │ + rate_limiter   │      │ db/health_repo      │
        │ + core/health    │      │ db/notification_repo│
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
- `name: str` — unique lowercase identifier (e.g., `"dhl"`)
- `priority: int` — higher wins when several trackers match the same ID
- `tracking_id_patterns: list[re.Pattern]` — regex matches for auto-detection
- `country_codes: list[str]` — informational, used by the future detection UI
- `async def fetch(tracking_id: str) -> TrackingResult` — the only mandatory method

### `TrackerRegistry`

Holds the built-in trackers (registered explicitly by `trackers.register_builtins()`) and
external plugins (drop-in `plugins/` dir, path overridable via `PARCEL_TRACKER_PLUGIN_DIR`).

### `CourierDetector`

Given a tracking ID, it returns every registered tracker whose patterns match, ordered by
`priority` desc (ties keep registration order). The scheduler tries them in that order and
falls back to the next one when a tracker fails or is quarantined, so the user does not need
to specify a carrier.

### `HealthManager`

Tracks per-tracker success/failure ratios, records consecutive failures, and quarantines a
tracker for `1h / 6h / 24h` after `3 / 6 / 12` consecutive failures of a
`(tracker, tracking_id)` pair; a tracker-wide entry, when present, blocks every code. The
scheduler checks `is_quarantined()` before each call and skips quarantined trackers.

### `Scheduler`

Runs every `STATUS_INTERVAL_*` minutes (per shipment status) in a single periodic Telegram job.
Each tick:
1. Pulls candidate parcels (`is_due()`).
2. Runs them in parallel batches of `BATCH_SIZE` (default 10).
3. Applies the per-tracker `RateLimiter` (token bucket).
4. Calls the matching trackers in priority order, recording success/failure in
   `HealthManager`.
5. Persists new events (deduplicated), updates statuses, and sends Telegram notifications
   gated by the user's per-status preferences. Events are marked notified only after a
   successful send, so a failed send is retried on the next tick.

### `Notifier` + `NotificationPreferences`

Per-user, per-status preferences; every status except the internal `NotFound` is on by
default. There is no time-based cooldown in the notification path: event deduplication
already prevents repeat messages. `NOTIFY_COOLDOWN_MINUTES` is parsed but currently unused.

### `Observability`

- `structlog` configured at startup; output is JSON in production, console in dev (`LOG_FORMAT`).
- `prometheus-client` serves the metrics listed in [observability.md](observability.md) on
  `:9090/metrics` (`METRICS_BIND_HOST`, `METRICS_PORT`).

## Data flow — `/add <tracking_id>` to first notification

```
User → Telegram → bot/parcel_commands.cmd_add
                  │
                  └─ ParcelRepository.create()   (writes parcels row)

Next scheduler tick (or "Update now" / "Refresh all" in the menu)
                  └─ scheduler._check_one()
                                          │
                                          ├─ CourierDetector.detect()
                                          ├─ Tracker.fetch()  (rate-limited, quarantine-aware)
                                          ├─ HealthManager.record_success/failure()
                                          ├─ ParcelRepository.add_events_dedup() / update_status()
                                          └─ TelegramNotifier.send_events_update()
                                                          │
                                                          └─ Telegram → User
```

## Persistence

SQLite via `aiosqlite`. WAL mode enabled. Schema lives in `src/parcel_tracker/db/migrations.py`
as a list of idempotent statements; each new schema change appends a statement guarded by
`IF NOT EXISTS`. No alembic in v0.1.x — too heavyweight for a single SQLite file.

Tables: `allowed_users`, `parcels`, `tracking_history`, `tracker_health`,
`user_notification_prefs`, `notification_cooldown_log` (the last one is currently unused).

## Plugin discovery — built-in vs drop-in

- **Built-in**: the trackers under `src/parcel_tracker/trackers/`, registered explicitly in
  `register_builtins()` (17track and the trackers backed by it only when `TRACK17_API_KEY`
  is set).
- **Drop-in**: every `*.py` under `plugins/` (or `$PARCEL_TRACKER_PLUGIN_DIR`) is imported
  at startup. Subdirectories are walked. Put your own plugins in `plugins/<country>/`
  (for example `plugins/it/` for Italian couriers such as BRT, GLS Italy, SDA, Poste
  Italiane); they are not shipped with the public repo.

## What is intentionally *not* here

- No SaaS / multi-tenant features. One bot, one owner, an allowlist of users.
- No web dashboard. Telegram is the only UI.
- No PostgreSQL/MySQL adapter. SQLite is enough; we will reconsider if we ever hit limits.
- No webhook mode for Telegram. Long polling is simpler and works behind NAT.
- No PyPI package. The supported install path is `git clone` + Docker.
