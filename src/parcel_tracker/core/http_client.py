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


def default_user_agents() -> list[str]:
    """Return the default User-Agent rotation pool."""
    return list(_DEFAULT_USER_AGENTS)


class HttpClient:
    """
    Async HTTP client wrapping httpx.AsyncClient with:
    - UA rotation per-request
    - Configurable timeout
    - Default headers for common scrape scenarios

    Used by tracker plugins. Phase 2 will add tenacity-based retry/backoff
    via the retry_policy module.
    """

    def __init__(
        self,
        *,
        timeout: float = 30.0,
        user_agents: list[str] | None = None,
    ) -> None:
        self._user_agents = user_agents or default_user_agents()
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
        return await self._client.get(url, params=params, headers=self._default_headers(headers))

    async def post(
        self,
        url: str,
        *,
        data: Any = None,
        json: Any = None,
        headers: dict[str, str] | None = None,
    ) -> httpx.Response:
        return await self._client.post(
            url, data=data, json=json, headers=self._default_headers(headers)
        )

    async def close(self) -> None:
        await self._client.aclose()
