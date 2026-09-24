# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.3.0] — 2026-06-07

### Added
- Post-add name prompt: after adding a parcel without a name the bot asks for one
  (skippable; pasting another tracking number just adds it instead).
- Parcel detail card: opening a parcel from the menu (and `/status`) now shows name,
  code, localized status, carrier, last location, last event time and last check time.
- Live refresh: the "🔄 Update now" button queries the carrier on demand
  (rate-limit and quarantine aware), without duplicate notifications.
- Parcel names shown first in menu pickers, `/list` and `/history`.

### Changed
- **BREAKING**: `/add CODE [name]` — the name is now multi-word; the positional
  `carrier` argument was removed (carrier auto-detection covers it).
- Delivery confirmation no longer repeats the tracking code for unnamed parcels;
  update notifications for unnamed parcels include a rename hint.

### Fixed
- `/add CODE my package` no longer mis-parses `package` as a carrier override.
- Event timestamps in `/events` are now formatted (`dd/mm/YYYY HH:MM`) instead of raw ISO.

## [0.2.0] — 2026-06-04

A large UX + features release. The bot is now fully button-driven — you never
have to type a slash command — with self-hosted route maps on every update,
cleaner notifications, a complete delivery lifecycle, and real admin tooling.

### Added

- **Self-hosted maps** attached to status updates and `/map`: an offline
  GeoNames geocoder (no external geocoding service), OpenStreetMap static
  tiles (no account), a route polyline through the parcel's geocodable event
  chain (origin → current position), and a transport-mode icon
  (plane / ship / train / truck / parcel) drawn on the latest point.
- **Delivery lifecycle**: on a Delivered transition the bot asks the user to
  confirm receipt (Yes / No), archives confirmed parcels to `/history`, keeps
  polling disputed ("Not yet") deliveries, and offers Undo on auto-add.
- **Button-first navigation**: a tap-driven inline `/menu` tree (My parcels /
  Maps / Settings / Admin / Help). Per-parcel actions (refresh, events, map,
  rename, remove) and admin tools (users, stats, tracker health, delivered,
  cleanup) are all reachable by tapping. Actions that need text input
  (rename, authorise/revoke user) use a guided prompt that captures your next
  message — no slash command required.
- **Real `/stats`**: parcels by status, breakdown by carrier, tracking activity
  (event count, last check) and tracker health (quarantined count), with a
  correct authorised-user count that includes the owner.
- **Bundled GeoNames `cities15000` dataset** (CC-BY, attributed in `NOTICE`)
  with alternate-name indexing so local city names (e.g. Milano, Roma) resolve.

### Changed

- **Cleaner notifications**: the tracking number appears once, the carrier and a
  localized status label are shown, event timestamps are formatted as
  `dd/mm/YYYY HH:MM`, and the map (when available) carries the message as its
  caption.
- **Slim native command list**: the Telegram "/" menu now shows only
  `menu` / `list` / `help`; all admin functions live in the inline menu tree.
- `/rename` now persists the new name (ownership-scoped); `/checkall` now runs a
  real on-demand check of the user's active parcels.

### Fixed

- **Stale per-chat command scopes**: earlier versions pushed an expanded admin
  command list via `BotCommandScopeChat`, which overrode the default scope and
  kept showing the old, larger list. Startup now clears those per-chat scopes so
  the slim default applies.
- **Security**: per-user ownership enforced on parcel commands and confirmation
  callbacks (IDOR), an admin gate on the authorise/revoke-user flows, HTML
  escaping of untrusted values in bot output, a global error handler, and
  muting of token-bearing URLs in logs.
- Persist tracking events and refresh the denormalised latest-event fields used
  by `/status` and notifications; notify on new events OR a status change.

### Internationalisation

- Italian (`it`) translations for the v0.2 UI, including status labels, the
  stats block, menu buttons, pickers and guided prompts; English baseline.

## [0.1.1] — 2026-05-26

### Fixed

- **Periodic scheduler skipped the owner's parcels.** The update job built its
  list of users to poll from the allowed-users table only, which never contains
  the owner (authorised via `OWNER_ID`) nor `ALLOWED_USER_IDS` entries. With an
  empty table the job returned immediately, so no parcel was ever checked —
  statuses never refreshed and delivery notifications never fired. The job now
  polls the union of the allowed-users table, the owner, and the configured
  allow-list, so every authorised user's parcels are checked on each tick.

## [0.1.0] — 2026-05-10

Promoted from `v0.1.0-rc.1`. Includes 4 regression fixes found during a
smoke test of the container image, plus a UX standardisation pass on the bot
menu.

### Added

- **Tap-only navigation** via redesigned `/menu` inline keyboard: 4 top-level
  sections (Parcels / Settings / Advanced / Help) with sub-menus, plus an
  Admin section visible only to authorised admins. Every command reachable
  by tapping; slash syntax remains optional.
- **`set_my_commands` integration**: Telegram client dropdown ("/" button)
  now lists 12 public commands by default scope and an extended set (12 +
  10 admin extras) per-admin via `BotCommandScopeChat`. Both English and
  Italian variants pushed via `language_code='en'/'it'`.
- **Callback dispatcher** with prefix routing (`nav:*` / `action:*` /
  `prompt:*` / `parcel:*`) — replaces the previous stub that echoed the
  callback name. Pattern-restricted `CallbackQueryHandler` so prefix-specific
  handlers (`notify:*`, etc.) are no longer shadowed.

### Changed

- `cmd_list`, `cmd_checkall`, `cmd_help`, `cmd_map`, `cmd_health`,
  `cmd_notify_dispatch`, `cmd_lang`, `cmd_users`, `cmd_stats`, `cmd_delivered`,
  `cmd_clean` now reply via `update.effective_message`, making them invocable
  from both `CommandHandler` and `CallbackQueryHandler` contexts.

### Fixed

- **runtime (Py3.12)**: `main.py` re-establishes the asyncio event loop after
  `asyncio.run(build_bot_data())`. PTB v21 `run_polling()` internally calls
  `asyncio.get_event_loop()`, which on Python 3.12 raises `RuntimeError` when no
  loop exists in the current thread. Pre-3.12 auto-created a loop; 3.12 requires
  explicit management. Without this fix the container crash-looped on every
  start.
- **plugin loader**: `registry.load_from_directory()` now scans plugin
  directories recursively (`rglob`). Locale-organized overlays such as
  `plugins/it/*.py` were silently ignored by the previous top-level-only
  `glob`.
- **i18n availability**: `available_locales()` now checks the compiled
  `messages.mo` (gettext binary, what the runtime actually loads) instead of
  the source `messages.po`. Distributions only ship `.mo`, so the previous
  `.po` check yielded zero locales in production and rejected `/lang <code>`.
- **packaging**: Dockerfile builder stage now installs `gettext` and runs
  `msgfmt` against every `messages.po` before `pip install`. Setuptools
  `package-data` then finds the freshly compiled `.mo` files; deployed images
  no longer ship empty locale catalogs.

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
- 5 Tier D detection-only trackers: Amazon Logistics, China Post, EMS, Singapore Post, Japan Post. Delegates `fetch` to Track17 with carrier identity rebrand.
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

[Unreleased]: https://github.com/bernalli/parcel-tracker-bot/compare/v0.3.0...HEAD
[0.3.0]: https://github.com/bernalli/parcel-tracker-bot/compare/v0.2.0...v0.3.0
