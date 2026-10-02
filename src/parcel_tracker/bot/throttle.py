"""Per-user cooldowns for actions that fan out to the carriers.

/checkall and the manual refresh each trigger live carrier requests. Without a
per-user cooldown a single user can repeat them back to back and spend the
shared carrier rate budget (and the 17track quota) for everyone else.
"""

from __future__ import annotations

import math
import time
from collections.abc import Callable, Hashable

CHECKALL_COOLDOWN_S = 60.0
REFRESH_COOLDOWN_S = 20.0


class Cooldown:
    """Remembers the last accepted time per key; in-memory, single process."""

    def __init__(self, seconds: float, *, clock: Callable[[], float] = time.monotonic) -> None:
        self._seconds = seconds
        self._clock = clock
        self._last: dict[Hashable, float] = {}

    def wait_seconds(self, key: Hashable) -> int:
        """0 if ``key`` may proceed now (and record it), else whole seconds to wait."""
        now = self._clock()
        last = self._last.get(key)
        if last is not None and now - last < self._seconds:
            return max(1, math.ceil(self._seconds - (now - last)))
        self._last[key] = now
        if len(self._last) > 10_000:  # bound memory: forget entries already expired
            self._last = {k: t for k, t in self._last.items() if now - t < self._seconds}
        return 0


CHECKALL = Cooldown(CHECKALL_COOLDOWN_S)
REFRESH = Cooldown(REFRESH_COOLDOWN_S)
