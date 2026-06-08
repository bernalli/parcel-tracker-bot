"""The /notify UI default and the scheduler gate default must agree.

Regression guard for a past split-brain: notify_commands carried its own
``_DEFAULT_ON_VALUES`` (only 4 statuses) while the scheduler gate
(``preferences._DEFAULT_ON``) treated every non-NOT_FOUND status as on. The menu
then showed in-transit/pickup/etc. as OFF while the bot actually notified them.
"""

from __future__ import annotations

from parcel_tracker.bot.notify_commands import _NOTIFIABLE_STATUS, _resolve_enabled
from parcel_tracker.db.models import ShipmentStatus
from parcel_tracker.notifier.preferences import is_default_on


def test_in_transit_is_on_by_default() -> None:
    assert is_default_on(ShipmentStatus.IN_TRANSIT.value) is True
    assert is_default_on(ShipmentStatus.PICKUP.value) is True
    assert is_default_on(ShipmentStatus.INFO_RECEIVED.value) is True


def test_expired_is_on_by_default() -> None:
    # 17track emits "Expired"; the old hand-listed _DEFAULT_ON omitted it, so the
    # gate silently dropped Expired updates for every courier. Pin it on.
    assert is_default_on(ShipmentStatus.EXPIRED.value) is True


def test_default_on_is_exhaustive_except_not_found() -> None:
    """Every status except NOT_FOUND must be default-on, by construction."""
    expected = {s.value for s in ShipmentStatus if s is not ShipmentStatus.NOT_FOUND}
    actual = {s.value for s in ShipmentStatus if is_default_on(s.value)}
    assert actual == expected


def test_not_found_is_never_default_on() -> None:
    assert is_default_on(ShipmentStatus.NOT_FOUND.value) is False


def test_ui_default_matches_scheduler_default_for_every_status() -> None:
    """With no explicit prefs, the menu's shown state must equal the gate default."""
    for status in _NOTIFIABLE_STATUS:
        assert _resolve_enabled({}, status) is is_default_on(status.value)
