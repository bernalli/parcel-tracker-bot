# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.4.0] — 2026-10-09

The "shop" release: the bot becomes a shipment control room for small online
sellers — a web dashboard, customer tracking pages, CSV and a JSON API — and a
long list of correctness, security and documentation fixes from a full audit.

### Added

- **Web dashboard** (`WEB_ENABLED=true`): KPIs, shipments that need attention,
  weekly shipped/delivered chart, carrier performance, searchable and filterable
  shipment list, detail pages with timeline and route map, CSV import/export,
  settings. Password-less sign-in through a one-time link sent by `/web`. Light
  and dark themes, mobile layout, English and Italian. See `docs/web.md`.
- **Customer tracking pages**: a revocable public link per shipment showing only
  carrier data, under your shop name; created from the dashboard or the bot's
  🔗 Share button.
- **JSON API v1** with personal tokens (list, create, read, update, archive
  shipments; statistics) for shop integrations.
- **Seller fields** on every shipment: order reference, customer, destination,
  tags and notes — editable from the dashboard, the API, CSV, and the bot's
  📝 Details button; shown on the parcel card.
- **Seller mode**: delivered parcels are archived automatically with a short
  notice instead of the "did you receive it?" question.
- **Stalled-shipment alerts**: one warning when an active parcel has had no
  carrier news for `STALL_ALERT_DAYS` (default 7).
- **Bulk add**: several codes in one message (one per line, a numbered list, or
  comma-separated), in the dashboard, or from a `.csv` file sent to the bot;
  `/export` sends a CSV back. Exported cells that a spreadsheet would run as
  formulas are escaped.
- **Smarter pasting**: a code is found after a label (`Tracking: RR…IT`), inside
  a sentence or a carrier link, or printed in groups and followed by a name.
- **Official DHL tracking API** (`DHL_API_KEY`), run before the DHL and
  Deutsche Post scrapers.
- **UPU S10 validation**: international postal codes get their check digit
  verified and show the issuing postal operator (40 mapped) from the start.
- Codes pasted with spaces, dashes or full-width digits are normalised the same
  way everywhere.
- Prometheus gauges `parceltracker_active_parcels` (now populated) and
  `parceltracker_stalled_parcels`; Grafana dashboard in `docs/grafana/`.
- New brand in the project's blue (`#2447E0`): logo set for blue, light and
  dark backgrounds, cover, social preview, Telegram avatar and description
  image, rendered by `scripts/make_docs_art.py`. The dashboard uses the same
  blue in light and dark mode.
- `scripts/demo_web.py` (dashboard on demo data) and `scripts/i18n.py`
  (catalog maintenance).
- `/forgetme` self-service erasure and automatic data retention
  (`DATA_RETENTION_DAYS`).

### Changed

- **`CHECK_INTERVAL_MINUTES` now defaults to 5**: it is how often the scheduler
  wakes up, and per-status intervals (5/15/30/60 min) are honoured at last.
- `/web` joins the Telegram command list; welcome and help texts describe the
  new features.
- Every built-in tracker shares one HTTP client that honours `REQUEST_TIMEOUT`
  and is closed on shutdown; drop-in plugins get it (and the 17track client)
  injected.
- Out-of-range settings (zero batch size, zero rate limit, bad ports, negative
  intervals, a non-URL `WEB_PUBLIC_URL`) stop the bot at startup.
- The UI language is per user; public pages follow the browser.
- Docker publishes the dashboard on `127.0.0.1:8080`.

### Removed

- `UPS_CLIENT_ID`, `UPS_CLIENT_SECRET`, `FEDEX_API_KEY`, `FEDEX_SECRET_KEY` and
  `NOTIFY_COOLDOWN_MINUTES`: they were documented but never used.
- `.env.example` entries that were never implemented
  (`URGENT_CHECK_INTERVAL_MINUTES`, `MAX_CONSECUTIVE_ERRORS`,
  `AUTO_ARCHIVE_HOURS`, `REQUEST_DELAY_*`).
- The never-populated `parceltracker_db_query_duration_seconds` metric.

### Fixed

- `/web` and `/export` refuse to answer in group chats, where anyone could
  open the sign-in link or read the customer list.
- The dashboard's sign-in refuses forms posted from another site (login CSRF),
  and a malformed CSRF value is a 403 instead of a server error.
- CSV import reads files with Mac line endings and reports a malformed file
  instead of failing with a server error.
- Erasing a user's data no longer lets their language choice come back after a
  restart, and no tracking history is written for a parcel erased during a
  carrier check.
- Out-of-range ids in dashboard URLs are a 404 instead of a server error.
- Every scraper read "not delivered", "undelivered", "nicht zugestellt",
  "non livré"… as **Delivered**, prompting a false receipt and stopping
  polling. A shared multilingual negation check now runs first.
- A batch of not-yet-scanned labels could quarantine a whole carrier for every
  user: "not found" no longer counts as a carrier failure.
- Re-adding an archived delivered parcel never tracked it again.
- A fallback source answering "not found" overwrote a known status, and a
  lagging source could re-open a delivery and prompt twice.
- Checks continued on parcels removed or erased mid-fetch; duplicate delivery
  prompts when a manual refresh raced the background sweep.
- A status change without new events was lost when Telegram failed to send it.
- Parcels were polled half as often as configured (drift between ticks).
- Parcels of `ADMIN_USER_IDS` users were never polled.
- An admin could wipe the owner's data with `/removeuser`; an abandoned
  "authorise user" prompt could turn a pasted number into an authorised user.
- Product names such as "AirPods2023" sent at the name prompt became parcels.
- `/status`, `/events`, `/remove`, `/rename` and `/map` failed for lower-case
  codes; non-ASCII codes broke Telegram buttons.
- Status labels, `/whoami`, `/stats` and notification buttons were always in
  English; `/lang` showed the wrong current language.
- An Australia Post pattern captured all-digit FedEx numbers.
- Event history was ordered by insertion, not by event time.
- The geocoder read US state codes as countries ("Berlin, DE" stays Germany,
  "Sacramento, CA" is California).
- The redirect guard accepted loopback shorthands (`127.1`, `2130706433`).
- Endless retries (and map renders) for users who blocked the bot.
- `/health <name>` did not find mixed-case plugin names; plugins defining
  dataclasses failed to load; 17track-backed plugins never got a 17track client.
- `/stats` counted single quarantined codes as quarantined trackers; per-code
  health rows kept tracking codes forever.
- Auto-add replied to every message in group chats; edited messages re-ran
  commands.
- Earlier in this cycle: central authorisation gate, per-user cooldowns on
  `/checkall` and refresh, retries and error classes for carrier requests, 5 MB
  response cap, safe redirects, plugin isolation, long updates split under
  Telegram's limits, terminal notifications retried, checks of one parcel
  serialised, input validation and escaping, erasure on user removal, tracking
  codes hashed in logs, pinned CI actions and Docker base image.

### Documentation

- New: `docs/web.md`, `docs/sellers.md`, `docs/operations.md`,
  `CODE_OF_CONDUCT.md`.
- Rewritten to match the code: README, `docs/trackers.md` (honest source tiers),
  `docs/plugins.md` (the examples are now tested), `docs/api-keys.md`,
  `docs/architecture.md`, `docs/observability.md`, `docs/i18n.md`,
  `docs/troubleshooting.md`.

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
- 1 integration test for scheduler fallback (3 scenarios).
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
- Notifications: `user_notification_prefs` + `notification_cooldown_log` tables, defaults DELIVERED/EXCEPTION/OUT_FOR_DELIVERY/RETURNED ON, configurable cooldown
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
