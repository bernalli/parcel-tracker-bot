from parcel_tracker.main import COMMANDS_PUBLIC_EN, COMMANDS_PUBLIC_IT


def test_public_command_list_is_slim() -> None:
    names_en = [c for c, _ in COMMANDS_PUBLIC_EN]
    assert names_en == ["start", "menu", "list", "help"]
    assert [c for c, _ in COMMANDS_PUBLIC_IT] == names_en
