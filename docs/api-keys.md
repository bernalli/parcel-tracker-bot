# Courier API keys

Most built-in scrapers work with **zero configuration** — they parse the public tracking
website. A handful of trackers (Tier D + 17track fallback) require a free API key from
17track. The DHL/UPS/FedEx native API endpoints are **optional** and only kick in if you
provide credentials; otherwise the public scraper paths are used.

## At a glance

| Tracker            | Required env var(s)                       | Cost (free tier)                | Sign-up                                  |
|--------------------|-------------------------------------------|---------------------------------|------------------------------------------|
| 17track (universal)| `TRACK17_API_KEY`                         | 100 quotas / day on Free tier   | https://api.17track.net/                 |
| Amazon Logistics   | `TRACK17_API_KEY`                         | (uses 17track)                  | (same)                                   |
| China Post         | `TRACK17_API_KEY`                         | (uses 17track)                  | (same)                                   |
| EMS                | `TRACK17_API_KEY`                         | (uses 17track)                  | (same)                                   |
| Singapore Post     | `TRACK17_API_KEY`                         | (uses 17track)                  | (same)                                   |
| Japan Post         | `TRACK17_API_KEY`                         | (uses 17track)                  | (same)                                   |
| DHL Express (opt)  | `DHL_API_KEY`                             | 250 calls/day on Free Plan      | https://developer.dhl.com                |
| UPS (opt)          | `UPS_CLIENT_ID`, `UPS_CLIENT_SECRET`      | Free for tracking, OAuth2       | https://developer.ups.com                |
| FedEx (opt)        | `FEDEX_API_KEY`, `FEDEX_SECRET_KEY`       | Free, OAuth2                    | https://developer.fedex.com              |

All other 19 Tier S trackers (USPS, Royal Mail, La Poste, Deutsche Post, Aramex, Australia
Post, Canada Post, Correos, Correios, FedEx scraper fallback, DPD, GLS Europe, Yodel, Evri,
Bpost, PostNL, Österreichische Post, Swiss Post, DHL scraper fallback) require **no key**.

## 17track (recommended)

Sign up: https://api.17track.net/

1. Register (Google / GitHub / email).
2. Go to **Console → API Settings**.
3. Create an API key.
4. Set it in your environment file:

```
TRACK17_API_KEY=ABC123…
```

The Free tier gives 100 quotas/day and lets you register a tracking number for periodic
push (we currently use the pull endpoint). For most personal users this is plenty.

## DHL Express (optional)

The bot ships a public scraper for DHL Express that needs no key. The OAuth2 API path is
faster and more reliable but requires a DHL Developer Portal account.

1. https://developer.dhl.com → register.
2. Create an app → request access to **Shipment Tracking** product.
3. Once approved (usually same-day) you get an API key.
4. Set `DHL_API_KEY` in your environment file. The bot picks the API path automatically when present.

## UPS (optional)

1. https://developer.ups.com → register.
2. Create an app → enable the **Tracking API**.
3. Generate Client ID + Client Secret.
4. Set `UPS_CLIENT_ID` and `UPS_CLIENT_SECRET`.

## FedEx (optional)

1. https://developer.fedex.com → register.
2. Create a project → enable **Track API**.
3. Generate API Key + Secret Key.
4. Set `FEDEX_API_KEY` and `FEDEX_SECRET_KEY`.

## Rotation & expiry

Most courier API keys are long-lived. UPS/FedEx use OAuth2 with short-lived access tokens
which the bot refreshes automatically. If you regenerate a key, just update your environment
file and `docker compose restart parcel-tracker`.

## Where keys *should not* go

- **Never** commit them. The environment file is in `.gitignore`.
- **Never** put them in `docker-compose.yml`. Use `env_file:` to load them from your
  local environment file.
- **Never** log them. The bot logs are sanitised but a careless plugin could still leak.
