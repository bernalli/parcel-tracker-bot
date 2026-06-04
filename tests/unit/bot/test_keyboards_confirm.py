from parcel_tracker.bot.keyboards import delivery_confirm_keyboard, undo_keyboard


def test_delivery_confirm_keyboard_has_yes_no() -> None:
    kb = delivery_confirm_keyboard("TN1")
    datas = [btn.callback_data for row in kb.inline_keyboard for btn in row]
    assert "confirm:yes:TN1" in datas
    assert "confirm:no:TN1" in datas


def test_undo_keyboard() -> None:
    kb = undo_keyboard("TN1")
    datas = [btn.callback_data for row in kb.inline_keyboard for btn in row]
    assert "confirm:undo:TN1" in datas
