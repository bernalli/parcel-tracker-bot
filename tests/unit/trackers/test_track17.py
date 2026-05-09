"""Tests for trackers.track17 — Track17Client fallback."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import respx

from parcel_tracker.db.models import ShipmentStatus
from parcel_tracker.trackers.track17 import Track17Tracker


@pytest.fixture
def track17() -> Track17Tracker:
    return Track17Tracker(api_key="fake_test_key")


def test_detects_anything() -> None:
    """Track17 is universal fallback: priority 1, matches any string."""
    t = Track17Tracker(api_key="x")
    assert t.detect("LITERALLY_ANYTHING") is True
    assert t.priority == 1


@pytest.mark.asyncio
async def test_fetch_in_transit(track17: Track17Tracker, fixtures_dir: Path) -> None:
    payload = json.loads((fixtures_dir / "track17" / "in_transit.json").read_text())
    async with respx.mock(base_url="https://api.17track.net") as mock:
        mock.post("/track/v2.2/gettrackinfo").respond(200, json=payload)
        # Stub register endpoint as well (bot calls it on first lookup)
        mock.post("/track/v2.2/register").respond(200, json={"code": 0})

        result = await track17.fetch("ABC123456")

    assert result.found is True
    assert result.status is ShipmentStatus.IN_TRANSIT
    assert result.tracking_number == "ABC123456"
