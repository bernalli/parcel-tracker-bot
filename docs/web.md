# Web dashboard and JSON API

The bot can serve a private web dashboard, public tracking pages for your
customers, and a JSON API. All three run inside the bot's own process, share its
database and trackers, and are off until you enable them.

<p align="center"><img src="img/dashboard.png" alt="Web dashboard with KPIs, shipments that need attention, a weekly chart and carrier statistics" width="860"></p>

## Enabling it

```dotenv
WEB_ENABLED=true
WEB_BIND_HOST=0.0.0.0              # inside Docker; 127.0.0.1 when running bare
WEB_PORT=8080
WEB_PUBLIC_URL=http://localhost:8080 # the address you open in the browser
```

`docker-compose.yml` publishes the port on `127.0.0.1:8080` only, so the
dashboard is reachable from the server itself. Restart, send `/web` to the
bot, and open the link it replies with.

`WEB_PUBLIC_URL` is used to build sign-in and tracking links. If you reach the
dashboard through a domain, set it to that `https://` address: cookies are then
marked `Secure`.

## Signing in

There are no passwords. `/web` sends a personal, single-use link that expires
after 15 minutes. Opening it shows a **Continue** button. Only that click signs
you in, so Telegram's link preview or a corporate link scanner cannot use the
link up. The session lasts `WEB_SESSION_DAYS` (default 30).

Anyone who can use the bot can use the dashboard, and sees only their own
shipments. Revoking a user in Telegram ends their dashboard sessions and API
tokens immediately. **Settings → Log out everywhere** ends all of your
sessions.

## Pages

| Page | What it is for |
|---|---|
| Dashboard | Active shipments, out for delivery today, shipments that need attention, deliveries in the last 30 days, median delivery time, success rate, weekly volume, carrier performance, recent deliveries |
| Shipments | Tabs (active, need attention, delivered, archived, all), search across code, name, order, customer, destination and notes, carrier and tag filters, CSV export of the current view |
| Shipment | Progress, carrier history, route map, check now, archive / restore / delete, customer tracking link, editable details |
| Add | One shipment with all fields, or many codes at once (one per line) |
| Import | CSV upload with a per-line report and a downloadable template |
| Settings | Seller mode, shop name, language, API tokens, log out everywhere, delete all my data |

"Need attention" lists active shipments with a carrier problem (undelivered,
exception, alert, returned, expired) and shipments with no carrier news for
`STALL_ALERT_DAYS` days.

## Customer tracking pages

From a shipment, **Create link** makes a public page at
`WEB_PUBLIC_URL/t/<random token>`. The bot's **🔗 Share** button does the same.
The page shows the status, the progress, the carrier history and the route map,
plus your shop name if you set one. It never shows the name you gave the
shipment, the order reference, the customer, the destination, tags or notes.
**Revoke** kills the address; **New link** replaces it. The page language
follows the visitor's browser.

<p align="center"><img src="img/public-page.png" alt="Public tracking page showing an out-for-delivery parcel" width="560"></p>

For customers to open these links, the dashboard must be reachable from the
internet: see [operations](operations.md#exposing-the-dashboard).

## CSV import and export

Export downloads every shipment (or the current filtered view) as UTF-8 CSV
with these columns:

```
tracking_number,name,order_ref,recipient,destination,tags,notes,carrier,status,
last_event,last_location,last_event_time,added_at,delivered_at,active
```

Import accepts the same file, a shop back-office export or a plain list:

- comma, semicolon or tab separated, with or without a UTF-8 BOM;
- headers in English or Italian (`codice`, `ordine`, `cliente`,
  `destinazione`, `note`, …), and common Spanish, French and German names;
- only the tracking number is required; without a recognised header the first
  column is read as codes and the second as names;
- up to 2,000 rows and 1 MB per file; duplicates are reported, not re-added.

Sending a `.csv` file to the bot in Telegram imports it the same way.

## JSON API

Create a token in **Settings → API tokens** (shown once, up to 20 per user) and
send it as a bearer token. Every call is scoped to the token's owner.

```bash
TOKEN=ptb_...
BASE=https://parcels.example.com/api/v1

curl -H "Authorization: Bearer $TOKEN" "$BASE/shipments?view=active"
```

| Method | Path | Description |
|---|---|---|
| `GET` | `/shipments` | List. Query: `view` (`active`, `attention`, `delivered`, `archived`, `all`), `q`, `carrier`, `tag`, `limit` (≤ 500), `offset` |
| `POST` | `/shipments` | Create. Body: `tracking_number` (required), `name`, `order_ref`, `recipient`, `destination`, `notes`, `tags` |
| `GET` | `/shipments/{code}` | One shipment; `?events=1` adds the carrier history |
| `PATCH` | `/shipments/{code}` | Update `name`, `order_ref`, `recipient`, `destination`, `notes`, `tags` (`null` clears) |
| `DELETE` | `/shipments/{code}` | Archive (stop tracking); `?purge=1` deletes it with its history |
| `GET` | `/stats` | Counters, delivery times and per-carrier statistics |

Create a shipment when an order ships:

```bash
curl -X POST "$BASE/shipments" \
  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{"tracking_number": "RR123456785IT", "order_ref": "#1042",
       "recipient": "Ada Lovelace", "destination": "Milano, IT", "tags": ["express"]}'
```

A shipment looks like this:

```json
{
  "id": 17,
  "tracking_number": "RR123456785IT",
  "name": null,
  "order_ref": "#1042",
  "recipient": "Ada Lovelace",
  "destination": "Milano, IT",
  "notes": null,
  "tags": ["express"],
  "carrier": "Poste Italiane",
  "status": "InTransit",
  "status_group": "transit",
  "last_event": "In transit",
  "last_event_time": "2026-10-09T08:12:00Z",
  "last_location": "Bologna, IT",
  "active": true,
  "stalled": false,
  "created_at": "2026-10-08T16:02:11Z",
  "delivered_at": null,
  "last_check_at": "2026-10-09T08:15:00Z",
  "last_change_at": "2026-10-09T08:15:00Z",
  "share_url": null
}
```

`status` is one of `NotFound`, `InfoReceived`, `Pickup`, `InTransit`,
`Customs`, `OutForDelivery`, `Delivered`, `Undelivered`, `Exception`, `Alert`,
`Returned`, `Expired`. `status_group` is `pending`, `transit`,
`out_for_delivery`, `attention` or `delivered`.

Errors are JSON (`{"error": "..."}`) with the usual codes: `401` bad token,
`404` unknown shipment, `409` already tracked or active limit reached, `422`
invalid tracking number, `400` malformed request.

## Security model

- Sessions, login links and API tokens are random 256-bit values; the database
  stores only their SHA-256 digests.
- Cookies are `HttpOnly`, `SameSite=Lax`, and `Secure` when
  `WEB_PUBLIC_URL` is `https`. Every form carries a per-session CSRF token.
- A strict Content-Security-Policy allows only the dashboard's own scripts,
  styles and images; there are no third-party requests, fonts or analytics.
- `Referrer-Policy: no-referrer` keeps sign-in and share tokens out of other
  sites' logs; pages are `noindex` and not cached.
- Authorisation is checked on every request against the same rules as the bot.
- Route maps are rendered by the server, so a customer's browser never
  contacts a map provider.

## Trying it without a bot

```bash
python scripts/demo_web.py --port 8080
```

This seeds a demo shop in a temporary database, prints a sign-in link and
serves the dashboard. Add `--lang it` for Italian or `--maps` to render route
maps (downloads map tiles).
