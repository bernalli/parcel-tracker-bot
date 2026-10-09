# Tracking sources and API keys

The bot can read tracking data from three kinds of sources. For each parcel it
tries the matching sources from the most to the least specific, and moves on to
the next one when a source does not know the code or is unavailable.

| Source | Setup | Coverage | Reliability |
|---|---|---|---|
| **17track API** | `TRACK17_API_KEY` | 2,000+ carriers worldwide | High. Recommended for everyone. |
| **DHL official API** | `DHL_API_KEY` | DHL Express, DHL Paket / Deutsche Post, DHL eCommerce | High |
| **Built-in web scrapers** | none | 20 national carriers (see [trackers](trackers.md)) | Best effort: carrier websites change and many render tracking with JavaScript |

Without any key the bot still works for the carriers whose public pages it can
read. With a 17track key every parcel has a reliable fallback. That is the
setup we recommend, and the one a shop should use.

## 17track (recommended)

1. Create an account at <https://api.17track.net>.
2. In the API console, copy your access key (sent as the `17token` header).
3. Put it in `.env`:

   ```dotenv
   TRACK17_API_KEY=your-key
   ```

The free plan includes a tracking quota that suits personal use; a shop sending
dozens of parcels a week needs a paid plan. 17track counts quota when a number
is registered; re-reading a registered number does not consume more.

17track also powers the detection-only trackers (Amazon Logistics, China Post,
EMS, Japan Post, Singapore Post). They recognise those codes and show the right
carrier name, but cannot fetch anything without a key.

## DHL (optional)

The DHL Shipment Tracking API is free and returns official data for most DHL
divisions from one endpoint.

1. Register at <https://developer.dhl.com>.
2. Create an app and add the **Shipment Tracking – Unified** API.
3. Copy the app's API key into `.env`:

   ```dotenv
   DHL_API_KEY=your-key
   RATE_LIMIT_TRACKER_DHL_API=10
   ```

When the key is set, DHL codes go to the official API first. The DHL and
Deutsche Post scrapers and 17track remain as fallbacks. The free plan allows
250 calls per day and about one call every five seconds. With the default
polling intervals that comfortably covers a dozen active DHL parcels; raise
`STATUS_INTERVAL_IN_TRANSIT` if you track more on the free plan.

A rejected key (HTTP 401/403) is logged as an error and counted as a tracker
failure, so the bot quarantines the API and keeps using the fallbacks.

## Rotation

API keys are read at startup. After changing one, restart the container:

```bash
docker compose up -d
```

## Where keys must not go

- Never commit `.env`; it is in `.gitignore`.
- Never put keys in `docker-compose.yml`; it loads them through `env_file`.
- Logs never include keys. Plugins you write yourself must not log them either.
