"""Tests for F0.5 — rich City, Country location + provider carrier in Track17Tracker."""

from __future__ import annotations

import pytest
import respx

from parcel_tracker.trackers.track17 import Track17Tracker

_PAYLOAD = {
    "data": {
        "accepted": [
            {
                "track_info": {
                    "latest_status": {"status": "InTransit"},
                    "latest_event": {
                        "description": "Departed facility",
                        "time_iso": "2026-06-02T08:00:00Z",
                        "address": {"city": "Milano", "state": "", "country": "Italy"},
                    },
                    "tracking": {
                        "providers": [
                            {
                                "provider": {"name": "BRT"},
                                "events": [
                                    {
                                        "time_iso": "2026-06-02T08:00:00Z",
                                        "description": "Departed facility",
                                        "address": {"city": "Milano", "country": "Italy"},
                                    }
                                ],
                            }
                        ]
                    },
                }
            }
        ]
    }
}


@pytest.mark.asyncio
async def test_track17_extracts_rich_location_and_carrier() -> None:
    t = Track17Tracker(api_key="x")
    async with respx.mock(base_url="https://api.17track.net") as mock:
        mock.post("/track/v2.2/register").respond(200, json={"code": 0})
        mock.post("/track/v2.2/gettrackinfo").respond(200, json=_PAYLOAD)
        result = await t.fetch("ABC123456")
    assert result.found is True
    assert result.last_location == "Milano, Italy"
    assert result.events[0].location == "Milano, Italy"
    assert result.events[0].carrier == "BRT"
