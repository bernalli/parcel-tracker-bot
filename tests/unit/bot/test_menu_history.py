from parcel_tracker.bot.keyboards import parcels_submenu


def test_parcels_submenu_has_history_button() -> None:
    kb = parcels_submenu()
    datas = [btn.callback_data for row in kb.inline_keyboard for btn in row]
    assert "action:history" in datas
