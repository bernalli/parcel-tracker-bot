# Plugins (drop-in custom trackers)

This directory is **gitignored** (except this README). Drop your custom tracker
plugins here as `.py` files, and they'll be auto-loaded at bot startup.

## Plugin contract

Each plugin file must define a `Tracker` class that subclasses `AbstractTracker`:

```python
# plugins/my_courier.py
import re
from parcel_tracker.core.tracker_base import AbstractTracker, TrackingResult
from parcel_tracker.db.models import ShipmentStatus

class Tracker(AbstractTracker):
    name = "my_courier"
    priority = 50  # 0-100, higher wins on ambiguous IDs
    country_codes = ["XX"]
    tracking_id_patterns = [re.compile(r"^MC\d{10}$")]
    url_patterns = [re.compile(r"mycourier\.com/track/")]

    async def fetch(self, tracking_id: str) -> TrackingResult:
        # Implement your scraping/API logic
        return TrackingResult(
            tracking_number=tracking_id,
            found=True,
            status=ShipmentStatus.IN_TRANSIT,
            carrier_name="My Courier",
        )
```

## Italian plugins (example use case)

If you're tracking Italian couriers (BRT, GLS Italy, SDA, Poste Italiane),
drop your plugins under `plugins/it/`:

```
plugins/
├── README.md         (this file, only one committed)
├── brt.py            (gitignored)
├── gls_italy.py      (gitignored)
├── sda.py            (gitignored)
└── poste_italiane.py (gitignored)
```

Plugins under nested subdirectories are also auto-loaded recursively.
