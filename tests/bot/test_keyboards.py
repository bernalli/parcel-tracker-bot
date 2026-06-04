# tests/bot/test_keyboards.py
from __future__ import annotations

from parcel_tracker.bot import keyboards
from parcel_tracker.db.models import Parcel


def _all_callbacks(markup) -> list[str]:
    return [btn.callback_data for row in markup.inline_keyboard for btn in row]


def test_main_menu_has_maps_entry_and_admin_when_admin() -> None:
    cb = _all_callbacks(keyboards.main_menu(is_admin=True))
    assert "nav:parcels" in cb
    assert "nav:maps" in cb
    assert "nav:admin" in cb


def test_main_menu_hides_admin_for_non_admin() -> None:
    cb = _all_callbacks(keyboards.main_menu(is_admin=False))
    assert "nav:admin" not in cb


def test_parcel_detail_keyboard_has_all_actions() -> None:
    cb = _all_callbacks(keyboards.parcel_actions_keyboard("TN1"))
    for action in ("refresh", "events", "map", "rename", "remove"):
        assert f"parcel:{action}:TN1" in cb


def test_picker_lists_parcels_with_action_prefix() -> None:
    parcels = [Parcel(tracking_number="A", user_id=1), Parcel(tracking_number="B", user_id=1)]
    cb = _all_callbacks(keyboards.parcel_picker_keyboard(parcels, "map"))
    assert "parcel:map:A" in cb and "parcel:map:B" in cb


def test_admin_submenu_complete() -> None:
    cb = _all_callbacks(keyboards.admin_submenu())
    for action in (
        "action:users",
        "action:stats",
        "action:health",
        "action:delivered",
        "nav:cleanup",
    ):
        assert action in cb


def test_settings_submenu_has_whoami() -> None:
    cb = _all_callbacks(keyboards.settings_submenu())
    assert "action:whoami" in cb
