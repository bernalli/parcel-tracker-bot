"""Per-tracker retry policies using tenacity.

Defines three ``RetryProfile`` presets suited to the different tracker
categories in this project:

- ``SCRAPING_FRAGILE``: unstable HTML-scraping endpoints (BRT, Poste, SDA)
  that suffer from intermittent 5xx / connection resets.
- ``OFFICIAL_API``: stable carrier REST APIs (DHL, UPS, FedEx) with known
  rate limits — fewer retries, longer back-off.
- ``UNIVERSAL_FALLBACK``: catch-all aggregator (17track) — minimal retries;
  after exhaustion the quarantine scheduler takes over (Bug #4 fix part 2).

Usage::

    from parcel_tracker.core.retry_policy import RetryProfile, apply_retry

    @apply_retry(RetryProfile.OFFICIAL_API)
    async def fetch(tracking_id: str) -> TrackingResult:
        ...

Wait-time neutralisation in tests
----------------------------------
The ``apply_retry`` decorator resolves ``wait_fixed`` / ``wait_exponential_jitter``
from this module's namespace at *call time* (inside ``wrapper``), not at
decoration time.  Test suites can therefore monkeypatch those two names in
this module's namespace to ``wait_fixed(0)`` and all retries will be instant.
See ``tests/unit/test_retry_policy.py`` for the ``_patch_retry_waits`` fixture.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import TypeVar

import httpx
from tenacity import (
    AsyncRetrying,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential_jitter,
    wait_fixed,
)

__all__ = ["RetryProfile", "RetryProfileConfig", "apply_retry"]

T = TypeVar("T")

# ---------------------------------------------------------------------------
# Retryable exception set — network-layer transients only.
# HTTP 4xx / 5xx are *not* retried here; trackers handle status codes.
# ---------------------------------------------------------------------------
_RETRYABLE_EXCEPTIONS = (
    httpx.ConnectError,
    httpx.ReadTimeout,
    httpx.ConnectTimeout,
    httpx.RemoteProtocolError,
    httpx.PoolTimeout,
)


# ---------------------------------------------------------------------------
# Profile data class
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class RetryProfileConfig:
    """Immutable configuration for a single retry strategy."""

    name: str
    max_attempts: int
    base_wait_seconds: float
    max_wait_seconds: float
    use_exponential: bool


# ---------------------------------------------------------------------------
# Built-in profiles
# ---------------------------------------------------------------------------


class RetryProfile:
    """Namespace for predefined retry strategies.

    SCRAPING_FRAGILE
        Aggressive retries for unstable scraping endpoints (BRT, Poste, SDA).
        5 attempts, exponential back-off 1-32 s.

    OFFICIAL_API
        Moderate retries for stable carrier APIs (DHL, UPS, FedEx).
        4 attempts, exponential back-off 2-16 s.

    UNIVERSAL_FALLBACK
        Limited retries for catch-all aggregator (17track).
        3 attempts, fixed 5 s wait.  Quarantine takes over after exhaustion.
    """

    SCRAPING_FRAGILE: RetryProfileConfig = RetryProfileConfig(
        name="scraping_fragile",
        max_attempts=5,
        base_wait_seconds=1.0,
        max_wait_seconds=32.0,
        use_exponential=True,
    )

    OFFICIAL_API: RetryProfileConfig = RetryProfileConfig(
        name="official_api",
        max_attempts=4,
        base_wait_seconds=2.0,
        max_wait_seconds=16.0,
        use_exponential=True,
    )

    UNIVERSAL_FALLBACK: RetryProfileConfig = RetryProfileConfig(
        name="universal_fallback",
        max_attempts=3,
        base_wait_seconds=5.0,
        max_wait_seconds=5.0,
        use_exponential=False,
    )


# ---------------------------------------------------------------------------
# Decorator
# ---------------------------------------------------------------------------


def apply_retry(
    profile: RetryProfileConfig,
) -> Callable[[Callable[..., Awaitable[T]]], Callable[..., Awaitable[T]]]:
    """Return a decorator that wraps an async function with tenacity retry.

    The ``wait`` strategy is constructed inside ``wrapper`` (at call time)
    so that test fixtures can monkeypatch ``wait_fixed`` / ``wait_exponential_jitter``
    in this module's namespace to achieve zero-delay retries.

    Args:
        profile: A :class:`RetryProfileConfig` instance (use :class:`RetryProfile`
                 class attributes for the built-in presets).

    Returns:
        A decorator that adds retry behaviour to the target coroutine.

    Raises:
        The last exception raised by the wrapped coroutine after all attempts
        are exhausted (``reraise=True``).
    """

    def decorator(fn: Callable[..., Awaitable[T]]) -> Callable[..., Awaitable[T]]:
        async def wrapper(*args: object, **kwargs: object) -> T:
            # Resolve wait helpers at call-time — testable via monkeypatch.
            wait = (
                wait_exponential_jitter(
                    initial=profile.base_wait_seconds,
                    max=profile.max_wait_seconds,
                    jitter=0.5,
                )
                if profile.use_exponential
                else wait_fixed(profile.base_wait_seconds)
            )
            async for attempt in AsyncRetrying(
                stop=stop_after_attempt(profile.max_attempts),
                wait=wait,
                retry=retry_if_exception_type(_RETRYABLE_EXCEPTIONS),
                reraise=True,
            ):
                with attempt:
                    return await fn(*args, **kwargs)
            # Unreachable: reraise=True guarantees exception propagation.
            raise RuntimeError("retry loop exited without result")  # pragma: no cover

        return wrapper

    return decorator
