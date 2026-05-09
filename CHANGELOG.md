# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [v0.1.0-enhancements] — 2026-05-09

### Added
- structlog hybrid setup intercepting stdlib logging (JSON in prod, console in dev)
- Prometheus metrics exporter at `/metrics` (configurable port, no auth, scope via Docker network)
- 8 metrics: parceltracker_check_total/_check_latency_seconds, _quarantine_active, _telegram_sent_total/_errors_total, _db_query_duration_seconds, _scheduler_tick_duration_seconds, _active_parcels
- `/health`, `/health <name>`, `/health reset <name>` (admin) Telegram commands
- `/notify` command family: interactive keyboard, quick on/off/all/none, callback toggle
- Scheduler refactor: dynamic interval per ShipmentStatus, parallel batch via asyncio.gather, per-tracker token bucket rate limiter, priority queue
- Feature D notifications: `user_notification_prefs` + `notification_cooldown_log` tables, defaults DELIVERED/EXCEPTION/OUT_FOR_DELIVERY/RETURNED ON, configurable cooldown
- New env: LOG_LEVEL, LOG_FORMAT, METRICS_*, ADMIN_USER_IDS, BATCH_SIZE, RATE_LIMIT_*, NOTIFY_COOLDOWN_MINUTES

### Changed
- `core/scheduler.py` rewritten (parallel + dynamic interval + rate limit + priority)
- `notifier/telegram.py` instrumented with Prometheus counters
- `db/migrations.py` adds `parcels.last_check_at` column + 2 new tables (idempotent)
- `db/health_repository.py` reset_tracker also clears consecutive_successes (full counter reset)

### Dependencies
- + structlog ≥24.1
- + prometheus-client ≥0.20
- + freezegun ≥1.5 (dev only)

## [Unreleased]

### Added
- Initial scaffolding (pyproject, license, gitignore, pre-commit)

[Unreleased]: https://github.com/bernalli/parcel-tracker-bot/compare/v0.1.0...HEAD
