# Operations

Deploying, configuring, exposing, backing up and upgrading the bot. For how it
works inside, see [architecture](architecture.md); for metrics, see
[observability](observability.md).

## Deploying with Docker Compose

```bash
git clone https://github.com/bernalli/parcel-tracker-bot.git
cd parcel-tracker-bot
cp .env.example .env        # set TELEGRAM_BOT_TOKEN and OWNER_ID
docker compose up -d
docker compose logs -f parcel-tracker
```

The container runs as UID 1000 with a read-only root filesystem, no Linux
capabilities, `no-new-privileges`, and memory, CPU and process limits. The
database lives in the `parcel-tracker-data` volume; `./plugins` is mounted
read-only.

## Running without Docker

```bash
python3.12 -m venv .venv && . .venv/bin/activate
pip install -e .
python -m parcel_tracker.i18n.build      # compile translations
cp .env.example .env                     # set the token, OWNER_ID, DATABASE_PATH=./data/bot.db
parcel-tracker
```

## Configuration

Everything is read from the environment (or `.env`). `.env.example` lists
every variable with its default. The most important ones:

| Variable | Default | Purpose |
|---|---|---|
| `TELEGRAM_BOT_TOKEN` | required | Token from @BotFather |
| `OWNER_ID` | required | Your numeric Telegram ID; always an admin |
| `ALLOWED_USER_IDS`, `ADMIN_USER_IDS` | empty | Extra users and admins, comma-separated |
| `TRACK17_API_KEY` | empty | 17track, the universal source and fallback |
| `DHL_API_KEY` | empty | Official DHL tracking API |
| `CHECK_INTERVAL_MINUTES` | `5` | How often the scheduler wakes up |
| `STATUS_INTERVAL_<STATUS>` | see `.env.example` | Polling interval per status (minutes, `0` stops) |
| `MAX_ACTIVE_SHIPMENTS` | `20` | Per user; `0` = unlimited |
| `STALL_ALERT_DAYS` | `7` | Warn about parcels with no news for N days; `0` = off |
| `WEB_ENABLED` | `false` | Web dashboard, tracking pages and API |
| `WEB_PUBLIC_URL` | `http://localhost:8080` | Base of the links the bot sends |
| `DATA_RETENTION_DAYS` | `180` | Delete archived parcels after N days; `0` keeps them |
| `DEFAULT_LANGUAGE` | `en` | `en` or `it`; users can switch with `/lang` |
| `MAPS_ENABLED` | `true` | Route maps on notifications and in the dashboard |
| `METRICS_ENABLED` | `true` | Prometheus exporter on `METRICS_PORT` (9090) |

Invalid values (a zero batch size, a port out of range, a negative interval, a
non-URL `WEB_PUBLIC_URL`) stop the bot at startup with a clear message.

## Exposing the dashboard

By default the dashboard listens on `127.0.0.1:8080` of the host. To share
tracking pages with customers, put it behind a reverse proxy with TLS and set
`WEB_PUBLIC_URL` to the public address.

Caddy (automatic HTTPS):

```caddy
parcels.example.com {
    reverse_proxy 127.0.0.1:8080
}
```

nginx:

```nginx
server {
    listen 443 ssl http2;
    server_name parcels.example.com;
    # ssl_certificate / ssl_certificate_key …
    client_max_body_size 2m;
    location / {
        proxy_pass http://127.0.0.1:8080;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

```dotenv
WEB_PUBLIC_URL=https://parcels.example.com
```

To expose only the customer pages and keep the dashboard private, forward
just `/t/` and `/static/` publicly and reach the rest through a VPN or an
allow-listed IP.

Never publish the metrics port (9090) to the internet.

## Backup and restore

All state is in one SQLite file (`DATABASE_PATH`, default
`/app/data/bot.db`): users, shipments, history, settings, web sessions and
tokens. Take a consistent copy with SQLite's backup command while the bot runs:

```bash
docker compose exec parcel-tracker python -c \
  "import sqlite3; s=sqlite3.connect('/app/data/bot.db'); d=sqlite3.connect('/app/data/backup.db'); s.backup(d); d.close()"
docker compose cp parcel-tracker:/app/data/backup.db ./bot-$(date +%Y%m%d).db
```

To restore, stop the bot, copy the file back into the volume as `bot.db`, and
start it again. Older backups are upgraded automatically at startup.

## Using the published image

Each release is published on `ghcr.io/bernalli/parcel-tracker-bot` for amd64 and
arm64, signed with cosign, with its SBOM attached to the GitHub release.

| Tag | Points to |
|---|---|
| `0.4.0`, `0.4` | That release, or the newest patch of that minor version |
| `latest` | The newest stable release; release candidates never move it |
| `edge` | The current `main`, only when the Docker workflow is run by hand |

To use it instead of building locally, remove the `build: .` line from
`docker-compose.yml` and set `image: ghcr.io/bernalli/parcel-tracker-bot:0.4.0`.

## Upgrading

```bash
git pull
docker compose up -d --build
```

With the published image, change the tag in `docker-compose.yml` and run
`docker compose pull && docker compose up -d`.

Schema changes are applied automatically and idempotently at startup; take a
backup first. Read the [changelog](../CHANGELOG.md) for anything that changes
behaviour.

## Telegram profile

Give the bot a face: in @BotFather open your bot, then **Edit Bot**.

- Bot picture: `docs/img/logo/avatar-640.png`
- Description picture: `docs/img/telegram-description.png`
- Description: *Send a tracking number and I'll tell you when it moves. Route
  maps, delivery alerts and a web dashboard for sellers.*

On GitHub, upload `docs/img/social-preview.png` in **Settings → Social preview**.
