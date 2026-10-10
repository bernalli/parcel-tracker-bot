# Architecture

A 10 000-foot view of how `parcel-tracker-bot` is structured. For implementation details, read
the source — every module has a top-of-file docstring summarising its responsibility.

## Layered design

```
┌──────────────────────────────┐   ┌────────────────────────────────────┐
│ bot/  (Telegram)             │   │ web/  (aiohttp, optional)          │
│ handlers · parcel_commands · │   │ dashboard · public tracking pages │
│ seller_commands · callbacks  │   │ JSON API · auth (links, sessions)  │
└──────────────┬───────────────┘   └─────────────────┬──────────────────┘
               └──────────────┬─────────────────────┘
                 ┌────────────▼─────────────┐
                 │ core/shipments.py        │  one set of rules: normalise,
                 │ core/csv_io · core/stats │  validate, status groups, stalls
                 └────────────┬─────────────┘
        ┌─────────────────────┼───────────────────────┐
┌───────▼──────────┐ ┌────────▼─────────────┐ ┌───────▼───────────────────┐
│ core/scheduler   │ │ db/ repositories     │ │ notifier/telegram.py      │
│ + health, rate   │ │ parcels, users,      │ │ updates, delivery prompt, │
│   limiter, retry │ │ settings, web, health│ │ stall alerts, maps        │
└───────┬──────────┘ └──────────────────────┘ └───────────────────────────┘
        │
┌───────▼──────────────────────────────┐
│ core/registry · core/detector        │  tracking code → matching sources
└───────┬──────────────────────────────┘
┌───────▼──────────────────────────────┐
│ trackers/  APIs (17track, DHL),      │  one shared HttpClient
│ web scrapers, detection-only, plugins│
└──────────────────────────────────────┘
```

Everything runs in one process and one asyncio event loop: python-telegram-bot's
long polling, the scheduler job, and (when enabled) the aiohttp web server.

## Core concepts

### `AbstractTracker`

The plugin contract. A courier implementation declares:
- `name: str` — unique lowercase identifier (e.g., `"dhl"`)
- `priority: int` — higher wins when several trackers match the same ID
- `tracking_id_patterns: list[re.Pattern]` — regex matches for auto-detection
- `country_codes: list[str]` — informational only, not used for detection
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

Tracks health at two levels. Per shipment, a `(tracker, tracking_id)` pair is quarantined
for `1h / 6h / 24h` after `3 / 6 / 12` consecutive failures. Per tracker, every failure also
feeds an aggregate `(tracker, "")` circuit that trips after `12 / 24 / 48` consecutive
failures across shipments (a gap of more than 30 minutes since the last failure starts the
count again) and then blocks every code. A "not found" answer is not a failure: it only
backs off that one code, capped at the first tier, so a batch of unscanned labels cannot
quarantine a carrier. `/health` and the `parceltracker_quarantine_active` gauge read the
aggregate. Per-code rows of parcels no longer tracked are pruned every tick.

### `Scheduler`

A single repeating job wakes every `CHECK_INTERVAL_MINUTES` (default 5). Each tick:
1. Applies data retention and prunes stale health rows.
2. Lists active parcels of every authorised user (owner, admins, allow-list) and keeps the
   ones due under their status interval (`STATUS_INTERVAL_*`). All checks in a tick are
   stamped with the tick's start time, so intervals do not drift.
3. Re-sends pending notifications for parcels that left the polling set.
4. Checks due parcels, most urgent first, in parallel batches of `BATCH_SIZE`, each under a
   per-parcel lock shared with manual refreshes.
5. For each parcel: tries matching sources in priority order (rate-limited,
   quarantine-aware), re-reads the parcel (it may have been removed meanwhile), stores new
   events, guards against status regressions, and notifies. A status change without new
   events is stored only once its notification went out.
6. Sends stalled-shipment alerts (`STALL_ALERT_DAYS`), once per stall.

The delivery lifecycle depends on the user's mode: by default the user is asked to
confirm receipt; in seller mode they get a notice and the parcel is archived.

### `Notifier` + `NotificationPreferences`

Per-user, per-status preferences; every status except the internal `NotFound` is on by
default. There is no time-based cooldown: event deduplication already prevents repeat
messages. Messages are rendered in the recipient's language and split under Telegram's
limits; users who blocked the bot are not retried.

### Web layer

`web/server.py` builds an aiohttp application started from the bot's `post_init` hook.
Middlewares add security headers, authenticate API tokens, render HTML error pages, and
attach the browser session (with CSRF checks on POST). Pages are server-rendered Jinja
templates translated through the same gettext catalogs as the bot; charts are inline SVG.
See [web](web.md).

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

SQLite via `aiosqlite`, WAL mode. The schema lives in `src/parcel_tracker/db/migrations.py`
as idempotent statements and guarded `ALTER TABLE` steps, applied at every startup; an old
database is upgraded in place.

Tables: `parcels` (with the seller fields, share token and stall clock),
`tracking_history`, `allowed_users`, `user_language`, `user_notification_prefs`,
`user_settings`, `app_settings`, `tracker_health`, `web_sessions`, `web_login_tokens`,
`api_tokens`, `notification_cooldown_log` (legacy). `/forgetme` and user removal delete
every per-user row.

## Plugin discovery — built-in vs drop-in

- **Built-in**: the trackers under `src/parcel_tracker/trackers/`, registered in
  `register_builtins()`. 17track is registered when `TRACK17_API_KEY` is set and the
  official DHL tracker when `DHL_API_KEY` is set; the detection-only trackers are always
  registered and report "track17 not configured" without a key. All of them share one
  `HttpClient`, closed on shutdown.
- **Drop-in**: every `*.py` under `plugins/` (or `$PARCEL_TRACKER_PLUGIN_DIR`) is imported
  at startup, sub-directories included. A plugin that fails to import, construct or
  register (duplicate name) is logged and skipped. Plugins that accept `http_client` or
  `track17` in their constructor receive the shared instances. See [plugins](plugins.md).

## What is intentionally *not* here

- No SaaS / multi-tenant features. One deployment, one owner, an allow-list of users.
- No PostgreSQL/MySQL adapter. SQLite comfortably handles thousands of shipments.
- No webhook mode for Telegram. Long polling is simpler and works behind NAT.
- No JavaScript framework in the dashboard: server-rendered pages, a small script for
  progressive enhancement, no third-party requests.
- No PyPI package. The supported install path is Docker (or `pip install -e .`).
