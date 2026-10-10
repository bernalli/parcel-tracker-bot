# Writing a tracker plugin

Add a carrier without forking the project: drop one Python file into
`plugins/` (or the directory in `PARCEL_TRACKER_PLUGIN_DIR`) and restart the
bot. Sub-directories are scanned too, so `plugins/it/brt.py` works.

## Contract

- The file defines a class named **`Tracker`** that subclasses
  `AbstractTracker`.
- `name` is unique among all trackers. A duplicate is logged and the plugin is
  skipped; a plugin that fails to import or construct is skipped as well, and
  the bot keeps running.
- `fetch()` is `async` and returns a `TrackingResult`. It must not raise for
  ordinary failures: return `found=False` with an `error_kind`.
- The constructor may accept `http_client` and/or `track17` keyword arguments;
  the bot passes its shared HTTP client (connection pool, `REQUEST_TIMEOUT`,
  retries, safe redirects) and its 17track client when they exist.

## Example: an API-based courier

```python
"""plugins/acme.py — Acme Express via its JSON API."""

from __future__ import annotations

import re
from typing import ClassVar

from parcel_tracker.core.event_status import is_negated_delivery
from parcel_tracker.core.http_client import HttpClient
from parcel_tracker.core.tracker_base import (
    AbstractTracker,
    TrackingResult,
    classify_exception,
    classify_status,
)
from parcel_tracker.db.models import ShipmentStatus, TrackingEvent

_STATUS = {
    "LABEL": ShipmentStatus.INFO_RECEIVED,
    "PICKUP": ShipmentStatus.PICKUP,
    "TRANSIT": ShipmentStatus.IN_TRANSIT,
    "OUT": ShipmentStatus.OUT_FOR_DELIVERY,
    "DELIVERED": ShipmentStatus.DELIVERED,
    "FAILED": ShipmentStatus.UNDELIVERED,
}


class Tracker(AbstractTracker):
    name: ClassVar[str] = "acme"
    priority: ClassVar[int] = 70
    country_codes: ClassVar[list[str]] = ["US"]
    tracking_id_patterns: ClassVar[list[re.Pattern[str]]] = [re.compile(r"^ACME\d{10}$")]

    def __init__(self, *, http_client: HttpClient | None = None) -> None:
        self._http = http_client or HttpClient(timeout=30.0)

    async def fetch(self, tracking_id: str) -> TrackingResult:
        try:
            response = await self._http.get(f"https://api.acme.example/v1/parcels/{tracking_id}")
        except Exception as exc:  # noqa: BLE001 — report, never raise
            return TrackingResult(tracking_id, found=False, error=str(exc),
                                  error_kind=classify_exception(exc))
        if response.status_code != 200:
            return TrackingResult(tracking_id, found=False, error=f"HTTP {response.status_code}",
                                  error_kind=classify_status(response.status_code))
        data = response.json()
        events = [
            TrackingEvent(time=e["timestamp"], description=e["text"], location=e.get("city"))
            for e in data.get("events", [])  # newest first
        ]
        text = events[0].description if events else ""
        status = (ShipmentStatus.UNDELIVERED if is_negated_delivery(text)
                  else _STATUS.get(data.get("status", ""), ShipmentStatus.IN_TRANSIT))
        return TrackingResult(
            tracking_number=tracking_id,
            found=bool(events),
            status=status,
            carrier_name="Acme Express",
            carrier_code="acme",
            last_event=text or None,
            last_event_time=events[0].time if events else None,
            last_location=events[0].location if events else None,
            events=events,
        )
```

`TrackingResult` fields: `tracking_number`, `found`, `status`, `carrier_code`,
`carrier_name`, `last_event`, `last_event_time`, `last_location`, `events`
(newest first), `error`, `error_kind`. `TrackingEvent` fields: `time`,
`description`, `location`, `carrier`.

## Example: detection only, fetched through 17track

When 17track already covers a courier, a plugin only has to recognise its
codes and show the right name:

```python
"""plugins/it/brt.py — BRT codes, fetched through 17track."""

import re
from typing import ClassVar

from parcel_tracker.trackers._track17_backed import Track17BackedTracker


class Tracker(Track17BackedTracker):
    name: ClassVar[str] = "brt"
    priority: ClassVar[int] = 45
    country_codes: ClassVar[list[str]] = ["IT"]
    tracking_id_patterns: ClassVar[list[re.Pattern[str]]] = [re.compile(r"^\d{12}$")]
    CARRIER_NAME: ClassVar[str] = "BRT"
    CARRIER_CODE: ClassVar[str] = "brt"
```

`Track17BackedTracker` receives the bot's 17track client automatically and
re-brands the result with `CARRIER_NAME` / `CARRIER_CODE`. Without a
`TRACK17_API_KEY` it reports "track17 not configured".

## Rules of thumb

- **Patterns** are anchored (`^…$`) and as narrow as the carrier allows. A
  broad pattern steals codes from other trackers. Codes reach `detect()`
  already normalised: upper case, no spaces, dashes or dots.
- **Priority** decides the order among matches: official APIs 90–100, national
  scrapers 60–90, detection-only 30–45, 17track 1.
- **Errors**: use `classify_status()` / `classify_exception()` so the scheduler
  knows a 404 (try the next source) from a 503 (try again later) or a 429
  (stop, the quota is spent).
- **Health** is handled by the scheduler: never call `HealthManager` yourself.
- **Statuses**: check `is_negated_delivery()` before looking for "delivered".
- **Blocking work** (heavy parsing) goes through `asyncio.to_thread`; the bot
  is a single event loop.

## Testing a plugin

Mock HTTP with `respx` and cover at least: delivered, in transit, out for
delivery, not found, a malformed response, and detection (a matching code and a
foreign one). `tests/unit/trackers/test_dhl_api.py` is a compact template.

## Limits

Plugins run in the bot's process with its permissions: install only code you
trust. They cannot change core behaviour; if you need an extension point, open
an issue describing the use case.
