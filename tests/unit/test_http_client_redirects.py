from __future__ import annotations

import httpx
import pytest
import respx

from parcel_tracker.core.http_client import HttpClient, UnsafeRedirectError


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "location",
    [
        "http://127.0.0.1:8080/admin",
        "http://169.254.169.254/latest/meta-data/",
        "https://10.0.0.5/internal",
        "https://192.168.1.1/",
        "https://[::1]/",
        "https://localhost/",
        "https://bot.localhost/",
        "http://example.test/downgraded",
        "file:///etc/passwd",
    ],
)
async def test_unsafe_redirect_is_refused(location: str) -> None:
    client = HttpClient(timeout=5.0)
    async with respx.mock(assert_all_called=False) as mock:
        mock.get("https://example.test/track").respond(302, headers={"Location": location})
        internal = mock.route().respond(200, text="secret")
        with pytest.raises(UnsafeRedirectError):
            await client.get("https://example.test/track")
        assert not internal.called
    await client.close()


@pytest.mark.asyncio
async def test_public_https_redirect_is_followed() -> None:
    client = HttpClient(timeout=5.0)
    async with respx.mock() as mock:
        mock.get("https://example.test/track").respond(
            301, headers={"Location": "https://www.example.test/track?id=1"}
        )
        mock.get("https://www.example.test/track").respond(200, text="ok")
        r = await client.get("https://example.test/track")
        assert r.status_code == 200 and r.text == "ok"
    await client.close()


@pytest.mark.asyncio
async def test_relative_redirect_is_followed() -> None:
    client = HttpClient(timeout=5.0)
    async with respx.mock() as mock:
        mock.get("https://example.test/a").respond(302, headers={"Location": "/b"})
        mock.get("https://example.test/b").respond(200, text="ok")
        r = await client.get("https://example.test/a")
        assert r.text == "ok"
    await client.close()


@pytest.mark.asyncio
async def test_unsafe_redirect_is_not_retried() -> None:
    client = HttpClient(timeout=5.0)
    async with respx.mock() as mock:
        route = mock.get("https://example.test/track").respond(
            302, headers={"Location": "http://127.0.0.1/"}
        )
        with pytest.raises(httpx.HTTPError):
            await client.get("https://example.test/track")
        assert route.call_count == 1
    await client.close()
