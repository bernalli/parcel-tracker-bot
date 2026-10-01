from __future__ import annotations

import httpx
import pytest
import respx

from parcel_tracker.core.http_client import HttpClient


@pytest.mark.asyncio
async def test_oversized_body_is_rejected() -> None:
    client = HttpClient(timeout=5.0, max_response_bytes=1024)
    async with respx.mock(base_url="https://example.test") as mock:
        mock.get("/big").respond(200, content=b"A" * 10_000)
        with pytest.raises(httpx.HTTPError):
            await client.get("https://example.test/big")
    await client.close()


@pytest.mark.asyncio
async def test_normal_body_round_trips() -> None:
    client = HttpClient(timeout=5.0, max_response_bytes=1024)
    async with respx.mock(base_url="https://example.test") as mock:
        mock.get("/ok").respond(200, json={"a": 1})
        mock.post("/p").respond(201, text="created")
        r = await client.get("https://example.test/ok", params={"id": "RR123456789DE"})
        assert r.status_code == 200 and r.json() == {"a": 1}
        assert mock.calls[0].request.url.params["id"] == "RR123456789DE"
        r2 = await client.post("https://example.test/p", json={"x": 1})
        assert r2.status_code == 201 and r2.text == "created"
    await client.close()
