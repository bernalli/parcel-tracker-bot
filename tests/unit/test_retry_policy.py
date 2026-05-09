"""Tests for core.retry_policy — tenacity-based retry strategies.

Wait-bypass approach (a): autouse fixture patches `wait_fixed` and
`wait_exponential_jitter` inside the `parcel_tracker.core.retry_policy`
module namespace to return `wait_fixed(0)` (zero-delay).  This is done
*before* each test so that `apply_retry` picks up the patched callables
at decoration time (they are referenced inside `wrapper`, resolved lazily
per call).  Tests therefore complete in milliseconds.
"""

from __future__ import annotations

import httpx
import pytest

# Import real tenacity wait_fixed for the zero-delay patch value
from tenacity import wait_fixed

import parcel_tracker.core.retry_policy as _retry_mod
from parcel_tracker.core.retry_policy import (
    RetryProfile,
    apply_retry,
)

# ---------------------------------------------------------------------------
# Autouse fixture — neutralise all real waits for this test module
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _patch_retry_waits(monkeypatch: pytest.MonkeyPatch) -> None:
    """Replace tenacity wait helpers with zero-delay equivalents.

    `apply_retry` calls `wait_exponential_jitter(...)` and `wait_fixed(...)`
    at *wrapper-call-time* (inside `wrapper()`), so patching the names in
    the module namespace is sufficient — the patch is active for the whole
    test function.
    """
    zero = wait_fixed(0)
    monkeypatch.setattr(_retry_mod, "wait_exponential_jitter", lambda **kw: zero)
    monkeypatch.setattr(_retry_mod, "wait_fixed", lambda seconds: zero)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_retry_succeeds_after_transient_failures() -> None:
    attempts: list[int] = []

    @apply_retry(RetryProfile.UNIVERSAL_FALLBACK)
    async def flaky() -> str:
        attempts.append(1)
        if len(attempts) < 3:
            raise httpx.ReadTimeout("timeout")
        return "ok"

    result = await flaky()
    assert result == "ok"
    assert len(attempts) == 3


@pytest.mark.asyncio
async def test_retry_gives_up_after_max_attempts() -> None:
    attempts: list[int] = []

    @apply_retry(RetryProfile.OFFICIAL_API)
    async def always_fails() -> str:
        attempts.append(1)
        raise httpx.ReadTimeout("timeout")

    with pytest.raises(httpx.ReadTimeout):
        await always_fails()
    # OFFICIAL_API profile: max 4 attempts
    assert len(attempts) == 4


def test_retry_profile_thresholds() -> None:
    assert RetryProfile.SCRAPING_FRAGILE.max_attempts == 5
    assert RetryProfile.OFFICIAL_API.max_attempts == 4
    assert RetryProfile.UNIVERSAL_FALLBACK.max_attempts == 3
