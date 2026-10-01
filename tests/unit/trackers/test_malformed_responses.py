"""Every HTTP-backed tracker survives malformed carrier responses.

A carrier page that changed layout, an empty body, binary garbage or a
truncated document must yield ``found=False`` (or a well-formed result),
never an exception that escapes ``fetch``.
"""

from __future__ import annotations

import importlib
import json
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from parcel_tracker.core.http_client import HttpClient
from parcel_tracker.core.tracker_base import AbstractTracker, TrackingResult
from parcel_tracker.trackers.track17 import Track17Tracker

SCRAPERS: list[tuple[str, str, str]] = [
    ("aramex", "AramexTracker", "12345678901"),
    ("australia_post", "AustraliaPostTracker", "AB123456789AU"),
    ("bpost", "BpostTracker", "AB123456789BE"),
    ("canada_post", "CanadaPostTracker", "1234567890123456"),
    ("correios", "CorreiosTracker", "AB123456789BR"),
    ("correos", "CorreosTracker", "AB123456789ES"),
    ("deutsche_post", "DeutschePostTracker", "RR123456789DE"),
    ("dhl", "DhlTracker", "1234567890"),
    ("dpd", "DpdTracker", "12345678901234"),
    ("evri", "EvriTracker", "1234567890123456"),
    ("fedex", "FedexTracker", "123456789012"),
    ("gls_europe", "GlsEuropeTracker", "12345678901"),
    ("la_poste", "LaPosteTracker", "AB123456789FR"),
    ("oesterreichische_post", "OesterreichischePostTracker", "RR123456789AT"),
    ("postnl", "PostnlTracker", "3SABCD1234567"),
    ("royal_mail", "RoyalMailTracker", "AB123456789GB"),
    ("swisspost", "SwissPostTracker", "RR123456789CH"),
    ("ups", "UpsTracker", "1Z999AA10123456784"),
    ("usps", "UspsTracker", "9405511899560000000000"),
    ("yodel", "YodelTracker", "JD0000000000000000"),
]

MALFORMED_HTML: dict[str, str] = {
    "empty": "",
    "whitespace": " \n\t ",
    "binary": "\x00\xff\xfe\x00garbage\x00",
    "json_instead_of_html": '{"error": "rate limited"}',
    "truncated": "<html><body><table class='tracking-events'><tr><td>2026-05",
    "empty_rows": (
        "<html><body><table class='tracking-events shipment-events'>"
        "<tr></tr><tr><td></td><td></td><td></td><td></td></tr>"
        "<div class='tracking-event event'><span class='event-date date'></span></div>"
        "</table></body></html>"
    ),
    "deep_nesting": "<div>" * 2000 + "x" + "</div>" * 2000,
    "huge_text": "<html><body><p>" + "A" * 1_000_000 + "</p></body></html>",
}


def _response(status_code: int, text: str) -> MagicMock:
    response = MagicMock()
    response.status_code = status_code
    response.text = text
    response.content = text.encode("utf-8", "surrogatepass")

    def _json() -> Any:
        return json.loads(text)

    response.json = MagicMock(side_effect=_json)
    return response


def _scraper(module: str, cls: str, client: HttpClient) -> AbstractTracker:
    tracker_cls = getattr(importlib.import_module(f"parcel_tracker.trackers.{module}"), cls)
    tracker: AbstractTracker = tracker_cls(http_client=client)
    return tracker


@pytest.mark.asyncio
@pytest.mark.parametrize("body", list(MALFORMED_HTML.values()), ids=list(MALFORMED_HTML))
@pytest.mark.parametrize(("module", "cls", "code"), SCRAPERS, ids=[s[0] for s in SCRAPERS])
async def test_scraper_handles_malformed_html(module: str, cls: str, code: str, body: str) -> None:
    client = MagicMock(spec=HttpClient)
    client.get = AsyncMock(return_value=_response(200, body))
    result = await _scraper(module, cls, client).fetch(code)
    assert isinstance(result, TrackingResult)
    assert result.found is False
    assert result.events == []


MALFORMED_JSON: dict[str, str] = {
    "not_json": "<html>502 Bad Gateway</html>",
    "empty": "",
    "string": '"oops"',
    "list": "[]",
    "data_is_list": '{"code": 0, "data": []}',
    "accepted_is_null": '{"data": {"accepted": null}}',
    "accepted_item_is_string": '{"data": {"accepted": ["RR123456789DE"]}}',
    "providers_not_list": (
        '{"data": {"accepted": [{"number": "X", "track_info": {"tracking": {"providers": 5}}}]}}'
    ),
    "null_fields": (
        '{"data": {"accepted": [{"number": "X", "track_info": {"latest_status": null,'
        ' "latest_event": null, "tracking": {"providers": [{"provider": null,'
        ' "events": [{"description": null, "time_iso": null, "address": null}]}]}}}]}}'
    ),
}


@pytest.mark.asyncio
@pytest.mark.parametrize("body", list(MALFORMED_JSON.values()), ids=list(MALFORMED_JSON))
async def test_track17_handles_malformed_json(body: str) -> None:
    client = MagicMock(spec=HttpClient)
    client.post = AsyncMock(return_value=_response(200, body))
    result = await Track17Tracker("test-key", http_client=client).fetch("RR123456789DE")
    assert isinstance(result, TrackingResult)
    for event in result.events:
        assert isinstance(event.description, str)


@pytest.mark.asyncio
@pytest.mark.parametrize("status", [400, 401, 403, 429, 500, 503])
async def test_track17_handles_http_error_status(status: int) -> None:
    client = MagicMock(spec=HttpClient)
    client.post = AsyncMock(return_value=_response(status, '{"code": -18019901}'))
    result = await Track17Tracker("test-key", http_client=client).fetch("RR123456789DE")
    assert isinstance(result, TrackingResult)
    assert result.found is False
