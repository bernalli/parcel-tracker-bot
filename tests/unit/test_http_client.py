"""Tests for core.http_client — UA rotation, timeout config."""

from __future__ import annotations

import pytest
import respx

from parcel_tracker.core.http_client import HttpClient, default_user_agents


def test_default_user_agents_non_empty() -> None:
    agents = default_user_agents()
    assert len(agents) >= 3
    assert all("Mozilla" in ua for ua in agents)


@pytest.mark.asyncio
async def test_get_uses_rotating_ua() -> None:
    client = HttpClient(timeout=5.0)
    seen_uas: set[str] = set()
    async with respx.mock(base_url="https://example.test") as mock:
        mock.get("/").respond(200, text="ok")
        for _ in range(10):
            await client.get("https://example.test/")
        for call in mock.calls:
            seen_uas.add(call.request.headers.get("User-Agent", ""))
    await client.close()
    # At least 2 different UAs seen across 10 calls
    assert len(seen_uas) >= 2


@pytest.mark.asyncio
async def test_get_returns_response() -> None:
    client = HttpClient(timeout=5.0)
    async with respx.mock(base_url="https://example.test") as mock:
        mock.get("/foo").respond(200, json={"hello": "world"})
        response = await client.get("https://example.test/foo")
    await client.close()
    assert response.status_code == 200
    assert response.json() == {"hello": "world"}
