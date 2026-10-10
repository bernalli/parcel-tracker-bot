"""Guided text input: "send me the new name", "send the user ID to authorise", …

A button that needs free text stores a *pending* action in ``user_data``; the
next text message is consumed as its value. Pending actions expire after
PENDING_TTL_S and are dropped when the user taps any other button, so an
abandoned prompt can never swallow a message sent much later (say, a pasted
tracking number becoming a parcel name or an authorised user ID).
"""

from __future__ import annotations

import time
from typing import Any

PENDING_KEY = "pending"
PENDING_TTL_S = 600.0


def set_pending(context: Any, action: str, **values: str) -> None:
    """Arm a guided input; replaces any earlier one."""
    if context.user_data is None:
        return
    context.user_data[PENDING_KEY] = {"action": action, **values, "at": time.monotonic()}


def pop_pending(context: Any) -> dict[str, Any] | None:
    """Consume the pending action, or None when there is none or it has expired."""
    data = getattr(context, "user_data", None)
    if not data:
        return None
    pending = data.pop(PENDING_KEY, None)
    if not pending:
        return None
    armed = pending.get("at")
    if isinstance(armed, int | float) and time.monotonic() - armed > PENDING_TTL_S:
        return None
    return dict(pending)


def clear_pending(context: Any) -> None:
    data = getattr(context, "user_data", None)
    if data:
        data.pop(PENDING_KEY, None)
