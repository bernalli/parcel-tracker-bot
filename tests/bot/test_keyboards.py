# tests/bot/test_keyboards.py
from __future__ import annotations

from parcel_tracker.bot import keyboards
from parcel_tracker.bot.keyboards import name_prompt_keyboard, parcel_picker_keyboard
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


def test_picker_appends_extra_rows() -> None:
    from telegram import InlineKeyboardButton

    parcels = [Parcel(tracking_number="A", user_id=1)]
    extra = [[InlineKeyboardButton("🔄", callback_data="action:checkall")]]
    cb = _all_callbacks(keyboards.parcel_picker_keyboard(parcels, "open", extra_rows=extra))
    assert "parcel:open:A" in cb  # parcel buttons preserved
    assert "action:checkall" in cb  # extra footer row appended


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


def test_picker_label_uses_name_when_present() -> None:
    p = Parcel(tracking_number="1Z999AA10123456784", user_id=1, name="iPhone 15")
    kb = parcel_picker_keyboard([p], "open")
    btn = kb.inline_keyboard[0][0]
    assert btn.text == "iPhone 15"
    assert btn.callback_data == "parcel:open:1Z999AA10123456784"


def test_picker_label_falls_back_to_tracking_number() -> None:
    p = Parcel(tracking_number="1Z999AA10123456784", user_id=1)
    kb = parcel_picker_keyboard([p], "map")
    assert kb.inline_keyboard[0][0].text == "1Z999AA10123456784"


def test_picker_label_truncated_to_32_chars() -> None:
    long_name = "Scarpe da corsa ultra ammortizzate blu fluo taglia 44"
    p = Parcel(tracking_number="TN12345678", user_id=1, name=long_name)
    kb = parcel_picker_keyboard([p], "open")
    label = kb.inline_keyboard[0][0].text
    assert len(label) <= 32
    assert label.endswith("…")


def test_name_prompt_keyboard_skip_only() -> None:
    kb = name_prompt_keyboard("TN12345678")
    row = kb.inline_keyboard[0]
    assert len(row) == 1
    assert row[0].callback_data == "parcel:skipname:TN12345678"


def test_name_prompt_keyboard_with_undo() -> None:
    kb = name_prompt_keyboard("TN12345678", include_undo=True)
    row = kb.inline_keyboard[0]
    assert [b.callback_data for b in row] == [
        "parcel:skipname:TN12345678",
        "confirm:undo:TN12345678",
    ]
