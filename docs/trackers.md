# Carriers and tracking sources

The bot never asks which carrier a parcel uses. It normalises the code (case,
spaces, dashes and dots are ignored), finds every source whose pattern matches,
and tries them from the highest priority down. When a source does not know the
code, is unavailable or is quarantined, the next one is tried. 17track matches
every code, so with a `TRACK17_API_KEY` every parcel has a final fallback.

## Source types

| Type | How it works | Reliability |
|---|---|---|
| **Official API** | JSON API from the carrier or an aggregator, with a key | High |
| **Web scraper** | Reads the carrier's public tracking page | Best effort |
| **Detection only** | Recognises the code and names the carrier, fetches through 17track | As 17track |

Web scrapers are honest best effort. They are tested against representative
HTML, but carriers redesign their pages, block automated traffic or render
tracking with JavaScript. When a scraper cannot read a page it reports
"not found" and 17track takes over; after three misses the scraper is skipped
for that code for an hour. For a
shop, configure 17track and treat the scrapers as a free bonus.

## Priority ladder

| Name | Priority | Type | Carrier | Patterns |
|---|---|---|---|---|
| `dhl_api` | 95 | Official API (`DHL_API_KEY`) | DHL Express, DHL Paket, eCommerce | `^\d{10}$`, `^JD\d{18}$`, `^JJD\d{10,30}$`, `^\d{20}$`, `^[A-Z]{2}\d{9}DE$`, `^(?!TBA)[A-Z]{3}\d{9,12}$` |
| `ups` | 90 | Web scraper | UPS | `^1Z[A-Z0-9]{16}$` |
| `usps` | 90 | Web scraper | USPS | `^91\d{20}$`, `^94\d{20}$`, `^9\d{19}$`, `^E[A-Z]\d{9}US$` |
| `royal_mail` | 85 | Web scraper | Royal Mail | `^[A-Z]{2}\d{9}GB$` |
| `la_poste` | 85 | Web scraper | La Poste / Colissimo | `^[A-Z]{2}\d{9}FR$`, `^[A-Z0-9]{11,13}FR$` |
| `deutsche_post` | 85 | Web scraper | Deutsche Post | `^[A-Z]{2}\d{9}DE$`, `^\d{20}$` |
| `aramex` | 80 | Web scraper | Aramex | `^\d{11}$` |
| `australia_post` | 80 | Web scraper | Australia Post | `^[A-Z]{2}\d{9}AU$`, `^33[A-Z]{8}\d{8,12}$`, `^7…` with at least one letter |
| `canada_post` | 80 | Web scraper | Canada Post | `^\d{16}$`, `^[A-Z]{2}\d{9}CA$` |
| `correios` | 75 | Web scraper | Correios (BR) | `^[A-Z]{2}\d{9}BR$` |
| `correos` | 75 | Web scraper | Correos (ES) | `^[A-Z]{2}\d{9}ES$` |
| `dhl` | 70 | Web scraper | DHL | `^\d{10}$`, `^JD\d{18}$`, `^(?!TBA)[A-Z]{3}\d{9,12}$` |
| `dpd` | 70 | Web scraper | DPD | `^\d{14}$`, `^\d{17}$` |
| `fedex` | 70 | Web scraper | FedEx / TNT | `^\d{12}$`, `^\d{15}$`, `^\d{20}$`, `^\d{22}$`, `^GD\d{9}$`, `^[A-Z]{2}\d{9}TN$` |
| `gls_europe` | 70 | Web scraper | GLS | `^\d{11}$` … `^\d{14}$` |
| `evri` | 65 | Web scraper | Evri (Hermes UK) | `^H\d{15}$`, `^T\d{16}$`, `^\d{16}$` |
| `yodel` | 65 | Web scraper | Yodel | `^JD\d{16}$`, `^Y\d{14}$` |
| `bpost` | 60 | Web scraper | bpost | `^[A-Z]{2}\d{9}BE$`, `^32\d{16}$` |
| `oesterreichische_post` | 60 | Web scraper | Österreichische Post | `^[A-Z]{2}\d{9}AT$`, `^\d{12}$`, `^\d{14}$` |
| `postnl` | 60 | Web scraper | PostNL | `^3S[A-Z0-9]{9,13}$`, `^[A-Z]{2}\d{9}NL$` |
| `swisspost` | 60 | Web scraper | Swiss Post | `^[A-Z]{2}\d{9}CH$`, `^99\d{16}$` |
| `amazon_logistics` | 40 | Detection only | Amazon Logistics | `^TBA\d{10,12}$` |
| `china_post` | 35 | Detection only | China Post | `^[LRCES][A-Z]\d{9}CN$` |
| `ems` | 33 | Detection only | EMS | `^E[A-Z]\d{9}[A-Z]{2}$` |
| `singapore_post` | 32 | Detection only | Singapore Post | `^[A-Z]{2}\d{9}SG$` |
| `japan_post` | 31 | Detection only | Japan Post | `^[A-Z]{2}\d{9}JP$` |
| `track17` | 1 | Official API (`TRACK17_API_KEY`) | 2,000+ carriers | any code |

Numeric codes are ambiguous by nature (a 12-digit number can be FedEx, GLS or
Österreichische Post). The bot tries every match in order, so an ambiguous code
still ends up at the carrier that knows it.

## International postal codes (UPU S10)

Postal items such as `RR123456785IT`, `CP123456785DE` or `LX123456785CN` follow
the UPU S10 standard: two letters, eight digits, a check digit and the issuing
country. The bot validates the check digit and names the postal operator from
the country suffix (Poste Italiane, Deutsche Post, China Post and 37 more)
from the moment the parcel is added. Tracking goes through the national
scraper when there is one, otherwise through 17track.

## Couriers without a built-in source

BRT, GLS Italy, SDA, Poste Italiane domestic parcels, InPost, Packeta and most
regional couriers are covered by 17track. If you need direct support, write a
plugin: see [plugins](plugins.md).

## Status mapping

Every source maps the carrier's wording to one of twelve statuses:

```
NotFound, InfoReceived, Pickup, InTransit, Customs, OutForDelivery,
Delivered, Undelivered, Exception, Alert, Returned, Expired
```

Mappers check for negated deliveries first ("not delivered", "non consegnato",
"nicht zugestellt", "non livré", "no entregado", "não entregue",
"niet afgeleverd"), so a failed delivery is never mistaken for a delivery.
A source that answers "not found" for a parcel that already has a status does
not reset it, and a delivered parcel only re-opens when the carrier reports new
events.

## Adding a built-in tracker

1. Subclass `AbstractTracker` (scraper or API) or `Track17BackedTracker`
   (detection only). `dhl_api.py` and `ups.py` are good templates.
2. Accept `http_client: HttpClient | None = None` in `__init__`, so it shares
   the bot's connection pool and `REQUEST_TIMEOUT`.
3. Call `is_negated_delivery()` first in your status mapper.
4. Add fixtures under `tests/fixtures/trackers/<name>/` and tests under
   `tests/unit/trackers/test_<name>.py` (delivered, in transit, out for
   delivery, not found, malformed input, detection).
5. Register it in `trackers/__init__.py` and add a routing sample to
   `tests/core/test_detection_routing.py`.
