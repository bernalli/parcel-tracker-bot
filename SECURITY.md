# Security policy

## Reporting a vulnerability

**Please do not open a public GitHub issue.** Instead, use one of the private channels below
so we can coordinate a fix and a disclosure timeline.

### Preferred — GitHub Security Advisories

Open a private advisory: https://github.com/bernalli/parcel-tracker-bot/security/advisories/new

This creates a private space where the maintainer and you can collaborate on the fix.

### Alternative — direct email

Report privately via the GitHub Security Advisory link above — please do not use email.

Please include:
- A description of the issue and the affected component
- Steps to reproduce (PoC, even minimal, helps a lot)
- Affected version(s) — branch, tag, or commit SHA
- Your contact preference (we credit you in the advisory unless you ask not to be named)

We will acknowledge receipt within **3 working days** and provide a triage assessment within
**7 working days**. We follow a **90-day disclosure timeline** unless the bug is being
exploited in the wild, in which case we will accelerate.

## Supported versions

| Version | Status            |
|---------|-------------------|
| `0.4.x` | ✅ Supported       |
| `< 0.4` | ❌ Not supported   |

Only the latest minor on the latest major receives security fixes. Backports are best-effort.

## Scope

The scope of this policy is the **public** code in this repository:

- `src/parcel_tracker/` — the core engine, built-in trackers, Telegram bot and web dashboard
  (sign-in, sessions, CSRF, public tracking pages, JSON API)
- `Dockerfile`, `docker-compose.yml` — official container build
- CI/CD workflows in `.github/workflows/`

Out of scope:

- Third-party plugins distributed elsewhere
- Self-hosted deployments configured insecurely (e.g., bot token committed to public Git)
- Telegram, Docker, or upstream library vulnerabilities (please report those upstream)

## Hardening already in place

- Read-only container root filesystem
- `no-new-privileges` Linux capability flag
- Dropped all capabilities (`cap_drop: ALL`)
- Resource limits (CPU 1.0, memory 512 MB, PIDs 100)
- Non-root container user (UID 1000)
- Secret scanning (`gitleaks`) on every commit and weekly cron
- Dependency audit (`pip-audit` + Dependabot)
- SAST (`bandit`) in CI
- Carrier requests: 5 MB response cap, redirects only to public addresses over HTTPS
- Web dashboard: password-less single-use sign-in links, server-side sessions and API
  tokens stored as SHA-256 digests, HttpOnly/SameSite cookies, per-session CSRF tokens,
  strict Content-Security-Policy, `Referrer-Policy: no-referrer`, authorisation re-checked
  on every request, public tracking pages that never show the seller's own data

## Hardening you must do

- **Never commit your environment file.** It is excluded by `.gitignore` for a reason.
- Pin Docker image tags (`:v0.4.0`, not `:latest`) in production.
- Restrict `OWNER_ID` and `ALLOWED_USER_IDS` to your real Telegram IDs.
- If exposing `:9090/metrics`, put it behind authentication or restrict to a private network.
- Expose the web dashboard only over HTTPS (set `WEB_PUBLIC_URL=https://…` so cookies are
  `Secure`); consider publishing only `/t/` and `/static/` to the internet.
- Install plugins only from sources you trust: they run with the bot's permissions.

## Public disclosure log

Public CVEs and advisories are tracked at:
https://github.com/bernalli/parcel-tracker-bot/security/advisories
