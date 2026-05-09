# Troubleshooting

Common errors and how to fix them. If your problem is not here, open an issue with the
relevant `docker compose logs --tail=200` output.

## "TELEGRAM_BOT_TOKEN missing"

The bot exits at startup with `ConfigError: TELEGRAM_BOT_TOKEN missing`.

**Cause**: your environment file does not contain `TELEGRAM_BOT_TOKEN` or the token is empty.

**Fix**: get a token from `@BotFather` on Telegram, paste it as `TELEGRAM_BOT_TOKEN=...`, and
restart the container.

## "OWNER_ID missing"

Same shape as above. Get your Telegram numeric user ID from `@userinfobot` and set
`OWNER_ID=123456789`.

## Bot does not reply to messages

Check the logs:

```bash
docker compose logs -f parcel-tracker
```

Common causes:

- **You are not allowlisted.** Only `OWNER_ID` and `ALLOWED_USER_IDS` can talk to the bot.
  Add yourself with `/adduser <id>` from the owner account.
- **The token is wrong / revoked.** Telegram returns 401. Regenerate the token in `@BotFather`.
- **Network issue.** The container needs outbound HTTPS to `api.telegram.org`. If you run
  behind a corporate proxy, set `HTTPS_PROXY` in the environment.

## "tracker quarantined"

A tracker has failed too many times in a row and is locked out for 1–24 h. The bot keeps
working with other trackers; the failing one auto-recovers.

To inspect: `/health` (per-tracker dashboard) or `/health <name>` for details.

To force a manual reset (admin only — `ADMIN_USER_IDS` in your environment file):
`/health reset <name>`.

## Database is locked

```
sqlite3.OperationalError: database is locked
```

**Cause**: another process has an exclusive lock — typically a manual `sqlite3 bot.db`
session that did not commit, or two bot instances pointing at the same file.

**Fix**:
- Quit any external `sqlite3` shell.
- Make sure only one container is running: `docker compose ps`.
- The bot uses WAL mode, so concurrent reads are fine but writes serialise.

## Telegram parse_mode errors

```
telegram.error.BadRequest: Can't parse entities …
```

A user-supplied tracking name contains characters that look like HTML to Telegram (`<`, `>`,
`&`). The bot escapes user input in admin/health paths but if you see this in a custom
plugin, run user values through `html.escape()` before composing the message.

## "tracker_id IM06010000000000" looping in logs

This was the symptom of Bug #1 — fixed in `v0.1.0-foundation`. If you still see it, you are
on a pre-`v0.1.0` build. Update.

## Container restarts every 5 minutes

The healthcheck is failing. Check:

```bash
docker inspect --format='{{json .State.Health}}' parcel-tracker-bot
```

Most common cause is the SQLite file path being wrong (`DATABASE_PATH`). Verify the volume
mount and that `data/` is writable by UID 1000.

## High memory / CPU

The container has hard limits (`mem_limit: 512m`, `cpus: 1.0`). If you need more, override in
`docker-compose.override.yml`. Memory should sit well under 100 MB for ≤50 active shipments;
sustained higher usage suggests a leak — please open an issue.

## Logs are too verbose

Set `LOG_LEVEL=WARNING` and restart. The default is `INFO`.

## I want to run a single check manually

```bash
docker compose exec parcel-tracker python -m parcel_tracker.cli check <tracking_id>
```

(The CLI sub-command is provided by the `parcel-tracker` entry point.)
