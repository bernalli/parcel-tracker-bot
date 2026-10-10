"""The examples in docs/plugins.md load and work as real plugins."""

from __future__ import annotations

import re
from pathlib import Path

import respx

from parcel_tracker.core.http_client import HttpClient
from parcel_tracker.core.registry import TrackerRegistry
from parcel_tracker.db.models import ShipmentStatus
from parcel_tracker.trackers._track17_backed import Track17BackedTracker

DOC = Path(__file__).resolve().parents[2] / "docs" / "plugins.md"


def _examples() -> list[str]:
    return re.findall(r"```python\n(.*?)```", DOC.read_text(encoding="utf-8"), flags=re.S)


async def test_documented_plugins_load_and_fetch(tmp_path: Path) -> None:
    api_example, backed_example = _examples()
    (tmp_path / "acme.py").write_text(api_example)
    (tmp_path / "it").mkdir()
    (tmp_path / "it" / "brt.py").write_text(backed_example)
    client = HttpClient(timeout=5.0, retry_profile=None)
    registry = TrackerRegistry()
    loaded = registry.load_from_directory(tmp_path, inject={"http_client": client, "track17": None})
    assert loaded == 2

    brt = registry.get_by_name("brt")
    assert isinstance(brt, Track17BackedTracker)
    assert brt.detect("123456789012")

    acme = registry.get_by_name("acme")
    assert acme is not None and acme.detect("ACME1234567890")
    payload = {
        "status": "OUT",
        "events": [
            {"timestamp": "2026-10-09T08:00:00Z", "text": "Out for delivery", "city": "Austin"},
            {"timestamp": "2026-10-08T08:00:00Z", "text": "Picked up", "city": "Dallas"},
        ],
    }
    with respx.mock() as mock:
        mock.get("https://api.acme.example/v1/parcels/ACME1234567890").respond(200, json=payload)
        result = await acme.fetch("ACME1234567890")
        mock.get("https://api.acme.example/v1/parcels/ACME0000000000").respond(404)
        missing = await acme.fetch("ACME0000000000")
    assert result.found
    assert result.status is ShipmentStatus.OUT_FOR_DELIVERY
    assert result.last_location == "Austin"
    assert not missing.found
