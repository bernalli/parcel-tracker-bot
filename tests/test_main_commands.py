"""Test the native Telegram command list configuration."""

from __future__ import annotations

from parcel_tracker import main


def test_public_command_list_is_minimal() -> None:
    names = [c for c, _ in main.COMMANDS_PUBLIC_EN]
    assert names == ["menu", "list", "help"]


def test_no_admin_extra_command_scope_constant() -> None:
    # Admin functions live in the inline tree now; no native admin command list.
    assert not hasattr(main, "COMMANDS_ADMIN_EXTRA_EN") or main.COMMANDS_ADMIN_EXTRA_EN == []
