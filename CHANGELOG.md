# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.0-rc.1] — 2026-05-10

First public release candidate. Full feature set:

- 24 built-in couriers (19 Tier S + 5 Tier D) + 17track universal fallback
- Tracker health & auto-quarantine
- Fine-grained notification preferences with cooldown
- Prometheus metrics + structlog JSON logging
- i18n (English + Italian, per-user via `/lang`)
- Hardened container (read-only fs, no-new-privileges, dropped caps, resource limits)
- GitHub Actions CI (matrix py3.11/3.12, ruff, mypy strict, pytest 75 % coverage gate)
- Security: gitleaks, bandit, pip-audit, dependency-review, Dependabot
- 427 tests, 91.17 % coverage

## [v0.1.0-trackers] — 2026-05-09

### Added
- 19 Tier S full-scraper trackers: UPS, USPS, Royal Mail, La Poste, Deutsche Post, Aramex, Australia Post, Canada Post, Correos (ES), Correios (BR), FedEx (with TNT folded), DPD, GLS Europe, Yodel, Evri (Hermes rebrand), Bpost, PostNL, Oesterreichische Post, Swiss Post.
- 5 Tier D detection-only trackers: Amazon Logistics, China Post, EMS, Singapore Post, Japan Post. Delega `fetch` to Track17 with carrier identity rebrand.
- New `Track17BackedTracker` base class for Tier D pattern.
- Multi-locale status keyword mapping (EN/IT/PT/FR/DE/ES out-of-the-box).
- `docs/trackers.md` with complete tracker catalog.

### Changed
- `core/scheduler.py:_check_one` now iterates `matches[1:]` on failure: when
  the primary tracker fails (raises or returns `found=False`), the scheduler
  falls back to lower-priority matches until one succeeds. This makes the
  zero-setup design resilient: a broken site scraper no longer silences the
  user when Track17 is configured.
- Aramex regex tightened from `^\d{10,12}$` to `^\d{11}$` to free 10-digit
  AWB to DHL and 12-digit to FedEx.
- DHL regex narrowed with `(?!TBA)` negative lookahead so Amazon Logistics
  TBA-prefix IDs route to amazon_logistics.
- USPS regex extended to cover 22-digit IMpb prefix (`^94\d{20}$`).
- GLS Europe regex extended to include 13-digit IDs.
- PostNL regex widened to allow 12-13 char tail after `3S` prefix.
- China Post regex tightened from `^[LRCEABS][A-Z]\d{9}CN$` to
  `^[LRCES][A-Z]\d{9}CN$` (canonical UPU prefixes only).

### Tests
- 24 new tracker-specific test files with parametrized HTML fixture parsing.
- 1 integration test for scheduler fallback (3 scenarios, F0).
- 1 integration test for detection routing (25 sample tracking IDs + registration check).
- Baseline: 414 tests passing, coverage maintained.

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
