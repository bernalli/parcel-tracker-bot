# Built-in Trackers

This document lists all built-in trackers shipped with `parcel-tracker-bot`,
their detection patterns, and their tier classification.

## Tier model

- **Tier S — Full scraper**: HTTP request → HTML parse → events list + status
  mapping. Provides full event timeline and accurate carrier metadata.
- **Tier D — Detection + Track17 delegation**: Identifies the carrier from the
  tracking ID pattern, delegates fetch to Track17 (universal API),
  re-brands result with correct carrier identity. Used when scraping is
  unfeasible (login-bound, JS-rendered, geographically limited).
- **Track17 fallback** (priority=1): universal pattern, called when no
  domain-specific tracker matches OR all domain-specific trackers fail.

## Tier S trackers

| Name | Priority | Country | Sample ID pattern |
|---|---|---|---|
| `ups` | 90 | US, GLOBAL | `^1Z[A-Z0-9]{16}$` |
| `usps` | 90 | US | `^91\d{20}$` / `^94\d{20}$` / `^9\d{19}$` / `^E[A-Z]\d{9}US$` (`^94\d{20}$` added during pattern tuning) |
| `royal_mail` | 85 | GB | `^[A-Z]{2}\d{9}GB$` |
| `la_poste` | 85 | FR | `^[A-Z]{2}\d{9}FR$` / `^[A-Z0-9]{11,13}FR$` |
| `deutsche_post` | 85 | DE | `^[A-Z]{2}\d{9}DE$` / `^\d{20}$` |
| `aramex` | 80 | AE, GLOBAL | `^\d{11}$` (tightened from the earlier 10-12 digit range) |
| `australia_post` | 80 | AU | `^[A-Z]{2}\d{9}AU$` / `^33[A-Z]{8}\d{8,12}$` / `^7[A-Z0-9]{11,15}$` |
| `canada_post` | 80 | CA | `^\d{16}$` / `^[A-Z]{2}\d{9}CA$` |
| `correos` | 75 | ES | `^[A-Z]{2}\d{9}ES$` |
| `correios` | 75 | BR | `^[A-Z]{2}\d{9}BR$` |
| `dhl` | 70 | DE, GLOBAL | `^\d{10}$` / `^JD\d{18}$` / `^(?!TBA)[A-Z]{3}\d{9,12}$` (negative lookahead `(?!TBA)` prevents collision with Amazon Logistics) |
| `fedex` | 70 | US, GLOBAL | `^\d{12}$` / `^\d{15}$` / `^\d{20}$` / `^\d{22}$` / `^GD\d{9}$` / `^[A-Z]{2}\d{9}TN$` |
| `dpd` | 70 | DE, GB, FR, GLOBAL | `^\d{14}$` / `^\d{17}$` |
| `gls_europe` | 70 | DE, AT, BE, NL, GLOBAL | `^\d{11}$` / `^\d{12}$` / `^\d{13}$` / `^\d{14}$` (`^\d{13}$` added later) |
| `yodel` | 65 | GB | `^JD\d{16}$` / `^Y\d{14}$` |
| `evri` | 65 | GB | `^H\d{15}$` / `^T\d{16}$` / `^\d{16}$` (Hermes rebrand 2022) |
| `bpost` | 60 | BE | `^[A-Z]{2}\d{9}BE$` / `^32\d{16}$` |
| `postnl` | 60 | NL | `^3S[A-Z0-9]{9,13}$` / `^[A-Z]{2}\d{9}NL$` / `^LL\d{9}NL$` (tail widened to `{9,13}`, was `{9,11}`) |
| `oesterreichische_post` | 60 | AT | `^[A-Z]{2}\d{9}AT$` / `^\d{12}$` / `^\d{14}$` |
| `swisspost` | 60 | CH | `^[A-Z]{2}\d{9}CH$` / `^99\.\d{2}\.\d{6}\.\d{8}$` / `^99\d{16}$` |

## Tier D trackers

| Name | Priority | Country | Carrier name | Sample ID pattern |
|---|---|---|---|---|
| `amazon_logistics` | 40 | US, GLOBAL | Amazon Logistics | `^TBA\d{10,12}$` |
| `china_post` | 35 | CN | China Post | `^[LRCES][A-Z]\d{9}CN$` (tightened to the `[LRCES]` prefix) |
| `ems` | 33 | GLOBAL | EMS | `^E[A-Z]\d{9}[A-Z]{2}$` |
| `singapore_post` | 32 | SG | Singapore Post | `^[A-Z]{2}\d{9}SG$` |
| `japan_post` | 31 | JP | Japan Post | `^[A-Z]{2}\d{9}JP$` |

## Fallback

| Name | Priority | Pattern | Note |
|---|---|---|---|
| `track17` | 1 | `.+` | Universal, requires `TRACK17_API_KEY` env. Used when no domain-specific match OR all matches fail. |

## Italian carriers (overlay only, not in repo)

The following Italian carriers are NOT shipped with the repo. Add them yourself as a
local overlay (gitignored) in `plugins/it/`:

- BRT (Bartolini)
- GLS Italy
- SDA (Poste Italiane Express)
- Poste Italiane

To use them: drop `*.py` files into `plugins/` directory of your deploy.

## Status mapping

Each Tier S tracker maps the carrier-specific status text to the canonical
`ShipmentStatus` enum:

```
DELIVERED, OUT_FOR_DELIVERY, IN_TRANSIT, PICKUP, INFO_RECEIVED,
EXCEPTION, CUSTOMS, ALERT, UNDELIVERED, RETURNED, EXPIRED, NOT_FOUND
```

Multi-locale keyword fallback covers EN/IT/PT/FR/DE/ES out-of-the-box.
Sites in non-Latin scripts (China Post, Japan Post, Singapore Post) are
handled by Tier D + Track17 normalization.

## Adding a new tracker

1. Choose tier (S = full scraper, D = detection + Track17 delegation).
2. Pick priority not colliding with existing range (see ladder above).
3. Use `dhl.py` (Tier S example) or `_track17_backed.py` (Tier D base)
   as starting template.
4. Save 3-5 fixture HTML in `tests/fixtures/trackers/<name>/`,
   sanitized of PII.
5. Write parametrized test in `tests/trackers/test_<name>.py`.
6. Register in `trackers/__init__.py:register_builtins()`.
7. Run `pytest tests/core/test_detection_routing.py` — add a sample to
   the routing test.
