"""Shared async HTTP client with UA rotation and configured timeouts."""

from __future__ import annotations

import random
from typing import Any

import httpx

_DEFAULT_USER_AGENTS: list[str] = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_2) AppleWebKit/605.1.15 "
    "(KHTML, like Gecko) Version/17.2 Safari/605.1.15",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_2 like Mac OS X) AppleWebKit/605.1.15 "
    "(KHTML, like Gecko) Version/17.2 Mobile/15E148 Safari/604.1",
]


# Carrier pages are a few hundred KB at most; anything far larger is an error page
# loop, a misbehaving upstream or an attack, and must not be buffered whole.
MAX_RESPONSE_BYTES = 5 * 1024 * 1024


class ResponseTooLargeError(httpx.RequestError):
    """Raised when a response body exceeds ``max_response_bytes``."""


def default_user_agents() -> list[str]:
    """Return the default User-Agent rotation pool."""
    return list(_DEFAULT_USER_AGENTS)


class HttpClient:
    """
    Async HTTP client wrapping httpx.AsyncClient with:
    - UA rotation per-request
    - Configurable timeout
    - Default headers for common scrape scenarios

    Used by tracker plugins.
    """

    def __init__(
        self,
        *,
        timeout: float = 30.0,
        user_agents: list[str] | None = None,
        max_response_bytes: int = MAX_RESPONSE_BYTES,
    ) -> None:
        self._user_agents = user_agents or default_user_agents()
        self._max_bytes = max_response_bytes
        self._client = httpx.AsyncClient(
            timeout=httpx.Timeout(timeout, connect=10.0),
            limits=httpx.Limits(max_connections=10, max_keepalive_connections=5),
            follow_redirects=True,
        )

    def _pick_ua(self) -> str:
        return random.choice(self._user_agents)  # noqa: S311 (not crypto)

    def _default_headers(self, extra: dict[str, str] | None = None) -> dict[str, str]:
        headers = {
            "User-Agent": self._pick_ua(),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
        }
        if extra:
            headers.update(extra)
        return headers

    async def get(
        self,
        url: str,
        *,
        params: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> httpx.Response:
        request = self._client.build_request(
            "GET", url, params=params, headers=self._default_headers(headers)
        )
        return await self._send_capped(request)

    async def post(
        self,
        url: str,
        *,
        data: Any = None,
        json: Any = None,
        headers: dict[str, str] | None = None,
    ) -> httpx.Response:
        request = self._client.build_request(
            "POST", url, data=data, json=json, headers=self._default_headers(headers)
        )
        return await self._send_capped(request)

    async def _send_capped(self, request: httpx.Request) -> httpx.Response:
        """Send ``request`` and buffer at most ``max_response_bytes`` of the body."""
        response = await self._client.send(request, stream=True)
        try:
            declared = response.headers.get("Content-Length")
            if declared and declared.isdigit() and int(declared) > self._max_bytes:
                raise ResponseTooLargeError(f"response declares {declared} bytes", request=request)
            body = bytearray()
            async for chunk in response.aiter_bytes():
                body += chunk
                if len(body) > self._max_bytes:
                    raise ResponseTooLargeError(
                        f"response exceeds {self._max_bytes} bytes", request=request
                    )
        finally:
            await response.aclose()
        return httpx.Response(
            status_code=response.status_code,
            headers=response.headers,
            content=bytes(body),
            request=request,
            extensions=response.extensions,
        )

    async def close(self) -> None:
        await self._client.aclose()
