"""Smoke tests for navigation_commands."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from parcel_tracker.bot.navigation_commands import (
    cmd_help,
    cmd_map,
    cmd_menu,
    cmd_start,
)


def _make_update() -> MagicMock:
    update = MagicMock()
    update.message = MagicMock()
    update.message.reply_text = AsyncMock()
    update.effective_user = MagicMock()
    update.effective_user.id = 1
    return update


@pytest.mark.asyncio
async def test_cmd_start_shows_welcome() -> None:
    update = _make_update()
    context = MagicMock()
    await cmd_start(update, context)
    text = update.message.reply_text.call_args.args[0]
    assert "Parcel Tracker" in text


@pytest.mark.asyncio
async def test_cmd_help_shows_commands() -> None:
    update = _make_update()
    context = MagicMock()
    await cmd_help(update, context)
    text = update.message.reply_text.call_args.args[0]
    assert "/add" in text
    assert "/list" in text


@pytest.mark.asyncio
async def test_cmd_menu_returns_keyboard() -> None:
    update = _make_update()
    context = MagicMock()
    await cmd_menu(update, context)
    update.message.reply_text.assert_called_once()
    kwargs = update.message.reply_text.call_args.kwargs
    assert kwargs.get("reply_markup") is not None


@pytest.mark.asyncio
async def test_cmd_map_replies() -> None:
    update = _make_update()
    context = MagicMock()
    await cmd_map(update, context)
    text = update.message.reply_text.call_args.args[0]
    assert "Mappa" in text or "mappa" in text
