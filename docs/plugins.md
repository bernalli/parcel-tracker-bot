# Writing a tracker plugin

You can add support for a courier without forking the project. A plugin is a single Python
file dropped into `plugins/` (or `$PARCEL_TRACKER_PLUGIN_DIR`) at runtime.

## Skeleton

```python
"""Acme Express tracker (priority=70)."""

from __future__ import annotations

import re

from parcel_tracker.core.tracker_base import AbstractTracker, TrackingResult, TrackingEvent
from parcel_tracker.db.models import ShipmentStatus


class AcmeExpressTracker(AbstractTracker):
    name = "AcmeExpress"
    priority = 70
    country_codes = ["US"]
    tracking_id_patterns = [
        re.compile(r"^ACME\d{10}$"),
    ]
    url_patterns = [
        re.compile(r"https?://(www\.)?acme-express\.com/track/(?P<id>[A-Z0-9]+)"),
    ]

    async def fetch(self, tracking_id: str) -> TrackingResult:
        async with self.http_client() as client:
            response = await client.get(
                f"https://api.acme-express.com/v1/parcels/{tracking_id}",
                timeout=10.0,
            )
        response.raise_for_status()
        data = response.json()

        events = [
            TrackingEvent(
                timestamp=event["timestamp"],
                location=event.get("location", ""),
                description=event["description"],
                status=self._map_status(event["code"]),
            )
            for event in data.get("events", [])
        ]
        return TrackingResult(
            tracking_id=tracking_id,
            carrier_name=self.name,
            carrier_code="acme",
            status=events[-1].status if events else ShipmentStatus.NOT_FOUND,
            events=events,
        )

    @staticmethod
    def _map_status(code: str) -> ShipmentStatus:
        return {
            "PICKUP":    ShipmentStatus.PICKUP,
            "TRANSIT":   ShipmentStatus.IN_TRANSIT,
            "OUT":       ShipmentStatus.OUT_FOR_DELIVERY,
            "DELIVERED": ShipmentStatus.DELIVERED,
        }.get(code, ShipmentStatus.IN_TRANSIT)
```

Drop the file as `plugins/acme.py` (or `plugins/<region>/acme.py`). Restart the bot. Done.

## Pattern checklist

- **`name`** is unique across all loaded trackers. Collision = startup error.
- **`priority`** decides who wins on regex collisions. Use the table in [docs/trackers.md] as a
  reference. Tier S (national post / OAuth API) typically `≥60`, Tier D fallbacks `30–40`,
  17track `1`.
- **`tracking_id_patterns`** are anchored regexes (`^…$`). Be precise — over-broad regexes
  steal IDs from the right tracker.
- **`fetch`** is `async`. Use `self.http_client()` so requests share UA rotation, timeout, and
  the retry decorator in `core/retry_policy.py`.
- **Retry**: decorate `fetch` with `@apply_retry(profile=…)` if you want an explicit retry
  policy. The default is exponential backoff 2s→16s, max 4 attempts.
- **Health**: do not call `HealthManager` from inside `fetch`; the scheduler already wraps
  every call with `@health_aware`.

## Tier D — delegate to 17track

If the courier has no public API and 17track covers it, subclass `Track17BackedTracker`:

```python
from parcel_tracker.trackers._track17_backed import Track17BackedTracker
import re

class AcmeWeakTracker(Track17BackedTracker):
    name = "AcmeWeak"
    priority = 35
    country_codes = ["XX"]
    track17_carrier_id = 1234           # from 17track carrier list
    rebrand_carrier_name = "Acme Weak"
    tracking_id_patterns = [re.compile(r"^[Aa]\d{12}$")]
```

The base class fetches via 17track and rewrites `carrier_name` / `carrier_code` so the user
sees `Acme Weak` instead of `17track`.

## Tests

For every plugin, add a unit test in `tests/unit/trackers/test_<name>.py` and HTML fixtures
in `tests/fixtures/trackers/<name>/`. Mock HTTP via `respx`. Cover at least:

- `delivered` event sequence
- `in_transit` event sequence
- `out_for_delivery` event sequence
- `not_found` (404 / empty response)
- detection: `AcmeExpressTracker.detect("ACME1234567890")` returns `True`
- detection: false positive on a foreign ID returns `False`

The 24 built-in trackers each have eight tests. Lean on them as templates.

## Distributing a plugin

We have no plugin marketplace. If you want to share a plugin:

1. Open a PR adding the tracker to `src/parcel_tracker/trackers/` for inclusion in the next
   minor release.
2. Or publish it as your own GitHub repo and document the install path in your README
   (typical: clone into the bot's `plugins/` mount).

## Limits

- Each plugin file = one tracker class. Multiple classes per file work but are confusing.
- Plugins **cannot** monkey-patch core modules. If you need to extend behaviour, open an
  issue describing the use case so we can add an extension point.
- Plugins run inside the same Python process as the bot. Misbehaving plugins (infinite
  loops, blocking IO) will degrade the whole bot — keep `fetch` async and time-boxed.
