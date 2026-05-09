"""Token bucket rate limiter per tracker — async-safe via asyncio.Lock."""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass


@dataclass(slots=True)
class _Bucket:
    capacity: int
    refill_per_second: float
    tokens: float
    last_refill: float


class RateLimiter:
    """Token bucket rate limiter, one bucket per tracker.

    Default rate (per minute) applies to trackers not explicitly configured.
    `acquire(tracker)` blocks (await asyncio.sleep) until 1 token is available.
    """

    def __init__(self, default_rate_per_min: int = 10) -> None:
        self._buckets: dict[str, _Bucket] = {}
        self._locks: dict[str, asyncio.Lock] = {}
        self._default_rate = default_rate_per_min

    def configure(self, tracker: str, rate_per_min: int) -> None:
        """Set or replace the bucket configuration for a tracker."""
        capacity = rate_per_min
        refill = rate_per_min / 60.0
        self._buckets[tracker] = _Bucket(
            capacity=capacity,
            refill_per_second=refill,
            tokens=float(capacity),
            last_refill=time.monotonic(),
        )
        self._locks[tracker] = asyncio.Lock()

    async def acquire(self, tracker: str) -> None:
        """Acquire 1 token for the given tracker, awaiting refill if needed."""
        if tracker not in self._buckets:
            self.configure(tracker, self._default_rate)
        bucket = self._buckets[tracker]
        async with self._locks[tracker]:
            self._refill(bucket)
            if bucket.tokens < 1.0:
                wait = (1.0 - bucket.tokens) / bucket.refill_per_second
                await asyncio.sleep(wait)
                self._refill(bucket)
            bucket.tokens -= 1.0

    @staticmethod
    def _refill(bucket: _Bucket) -> None:
        now = time.monotonic()
        elapsed = now - bucket.last_refill
        bucket.tokens = min(
            float(bucket.capacity),
            bucket.tokens + elapsed * bucket.refill_per_second,
        )
        bucket.last_refill = now
