# parcel-tracker-bot

Self-hosted Telegram bot for tracking parcels across 30+ couriers worldwide.

> **Status:** Pre-release (under active development). First public release `v0.1.0` is being prepared.

## Quick start

```bash
git clone https://github.com/bernalli/parcel-tracker-bot.git
cd parcel-tracker-bot
cp .env.example .env
# Edit .env with your TELEGRAM_BOT_TOKEN, OWNER_ID, optional courier API keys
docker compose up -d
```

## Documentation

- [Architecture](docs/architecture.md)
- [Plugin tutorial](docs/plugins.md)
- [Courier API keys](docs/api-keys.md)
- [Observability](docs/observability.md)

## License

MIT — see [LICENSE](LICENSE).
