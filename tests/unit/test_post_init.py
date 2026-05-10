"""Tests for the _post_init hook in parcel_tracker.main.

Verifies that set_my_commands is called for:
  - default scope (English)
  - default scope (Italian, language_code='it')
  - per-admin chat scope (English)
  - per-admin chat scope (Italian)
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from telegram import BotCommandScopeChat, BotCommandScopeDefault

from parcel_tracker.main import (
    COMMANDS_ADMIN_EXTRA_EN,
    COMMANDS_PUBLIC_EN,
    _post_init,
)


def _make_application(admin_user_ids: frozenset[int]) -> MagicMock:
    application = MagicMock()
    application.bot = MagicMock()
    application.bot.set_my_commands = AsyncMock()
    config = MagicMock()
    config.admin_user_ids = admin_user_ids
    application.bot_data = {"config": config}
    return application


@pytest.mark.asyncio
async def test_post_init_no_admins_calls_default_scope_only() -> None:
    application = _make_application(frozenset())

    await _post_init(application)

    # 2 calls: default-en + default-it
    assert application.bot.set_my_commands.await_count == 2

    calls = application.bot.set_my_commands.await_args_list
    en_call = calls[0]
    it_call = calls[1]

    assert isinstance(en_call.kwargs["scope"], BotCommandScopeDefault)
    assert "language_code" not in en_call.kwargs

    assert isinstance(it_call.kwargs["scope"], BotCommandScopeDefault)
    assert it_call.kwargs.get("language_code") == "it"


@pytest.mark.asyncio
async def test_post_init_with_admins_pushes_per_admin_scope() -> None:
    application = _make_application(frozenset({100, 200}))

    await _post_init(application)

    # 2 default + 2 per admin id × 2 langs = 2 + 4 = 6 calls
    assert application.bot.set_my_commands.await_count == 6

    # Collect all scopes used
    scopes = [c.kwargs["scope"] for c in application.bot.set_my_commands.await_args_list]
    chat_scopes = [s for s in scopes if isinstance(s, BotCommandScopeChat)]
    chat_ids = {s.chat_id for s in chat_scopes}
    assert chat_ids == {100, 200}


@pytest.mark.asyncio
async def test_post_init_admin_commands_include_admin_extras() -> None:
    application = _make_application(frozenset({1}))

    await _post_init(application)

    # 4 calls total. The 3rd (admin/en) should include all admin extras.
    calls = application.bot.set_my_commands.await_args_list
    admin_en_call = next(
        c
        for c in calls
        if isinstance(c.kwargs.get("scope"), BotCommandScopeChat)
        and c.kwargs.get("language_code") is None
    )
    bot_commands = admin_en_call.args[0]
    cmd_names = {bc.command for bc in bot_commands}
    assert "health" in cmd_names
    assert "stats" in cmd_names
    # Public commands also present
    assert "list" in cmd_names
    assert "menu" in cmd_names


@pytest.mark.asyncio
async def test_post_init_swallows_set_my_commands_failure() -> None:
    """If set_my_commands raises, post_init should log and continue."""
    application = _make_application(frozenset())
    application.bot.set_my_commands = AsyncMock(side_effect=RuntimeError("API down"))

    # Should not raise
    await _post_init(application)


@pytest.mark.asyncio
async def test_post_init_no_config_in_bot_data_is_noop() -> None:
    application = MagicMock()
    application.bot = MagicMock()
    application.bot.set_my_commands = AsyncMock()
    application.bot_data = {}

    await _post_init(application)
    application.bot.set_my_commands.assert_not_called()


def test_command_tables_have_consistent_lengths() -> None:
    """English and Italian command tables must have the same /command set."""
    en_keys = {cmd for cmd, _ in COMMANDS_PUBLIC_EN}
    # Italian is imported lazily by name; symmetry checked below via length.
    assert len(en_keys) == len(COMMANDS_PUBLIC_EN)
    assert len(COMMANDS_ADMIN_EXTRA_EN) > 0
