"""Tests for token bucket per-tracker rate limiter."""

from __future__ import annotations

import asyncio
import time

import pytest

from parcel_tracker.core.rate_limiter import RateLimiter


@pytest.mark.asyncio
async def test_acquire_succeeds_when_bucket_full() -> None:
    limiter = RateLimiter(default_rate_per_min=60)
    start = time.monotonic()
    await limiter.acquire("dhl")
    elapsed = time.monotonic() - start
    assert elapsed < 0.05  # immediate, no wait


@pytest.mark.asyncio
async def test_acquire_waits_when_bucket_empty() -> None:
    # 60 per_min => 1 per_sec => after consuming all tokens, must wait ~1 sec for next.
    limiter = RateLimiter(default_rate_per_min=60)
    limiter.configure("track17", rate_per_min=60)
    # Drain the bucket (capacity = 60).
    for _ in range(60):
        await limiter.acquire("track17")
    start = time.monotonic()
    await limiter.acquire("track17")
    elapsed = time.monotonic() - start
    assert elapsed >= 0.5, f"expected wait >=0.5s, got {elapsed:.3f}"


@pytest.mark.asyncio
async def test_acquire_uses_default_rate_for_unknown_tracker() -> None:
    limiter = RateLimiter(default_rate_per_min=120)
    await limiter.acquire("unknown_tracker")  # auto-configures with default
    state = limiter._buckets["unknown_tracker"]
    assert state.capacity == 120


@pytest.mark.asyncio
async def test_configure_overrides_per_tracker() -> None:
    limiter = RateLimiter(default_rate_per_min=10)
    limiter.configure("dhl", rate_per_min=60)
    await limiter.acquire("dhl")
    assert limiter._buckets["dhl"].capacity == 60


@pytest.mark.asyncio
async def test_concurrent_acquires_are_serialized_per_tracker() -> None:
    """Two concurrent acquires on the same tracker do not double-spend tokens."""
    limiter = RateLimiter(default_rate_per_min=2)  # capacity=2
    limiter.configure("track17", rate_per_min=2)

    results: list[float] = []

    async def acquire_and_record() -> None:
        start = time.monotonic()
        await limiter.acquire("track17")
        results.append(time.monotonic() - start)

    # Three concurrent acquires; bucket starts at 2, so the 3rd must wait.
    await asyncio.gather(*[acquire_and_record() for _ in range(3)])
    fast = sum(1 for r in results if r < 0.05)
    slow = sum(1 for r in results if r >= 0.5)
    assert fast == 2
    assert slow == 1
