"""Tests for the central authorization gate (#15)."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from telegram import Update
from telegram.ext import ApplicationHandlerStop, TypeHandler

from parcel_tracker.bot.auth_gate import AUTH_GATE_GROUP, authorization_gate, is_authorized
from parcel_tracker.bot.handlers import register_handlers

OWNER = 1
ENV_ALLOWED = 2
ADMIN = 3
DB_ALLOWED = 4
STRANGER = 99


def _context() -> Any:
    config = SimpleNamespace(
        owner_id=OWNER, allowed_user_ids=[ENV_ALLOWED], admin_user_ids=frozenset({ADMIN})
    )
    user_repo = MagicMock()
    user_repo.get_allowed_user_ids = AsyncMock(return_value=[DB_ALLOWED])
    return SimpleNamespace(bot_data={"config": config, "user_repo": user_repo})


def _message_update(user_id: int | None, text: str = "/add ABC123") -> Any:
    update = MagicMock(spec=Update)
    update.effective_user = None if user_id is None else SimpleNamespace(id=user_id)
    update.callback_query = None
    update.message = MagicMock()
    update.message.text = text
    update.message.reply_text = AsyncMock()
    return update


def _callback_update(user_id: int) -> Any:
    update = MagicMock(spec=Update)
    update.effective_user = SimpleNamespace(id=user_id)
    update.message = None
    update.callback_query = MagicMock()
    update.callback_query.answer = AsyncMock()
    return update


@pytest.mark.parametrize("user_id", [OWNER, ENV_ALLOWED, ADMIN, DB_ALLOWED])
async def test_authorised_users_pass(user_id: int) -> None:
    update = _message_update(user_id)
    await authorization_gate(update, _context())  # no ApplicationHandlerStop
    update.message.reply_text.assert_not_awaited()


async def test_stranger_command_is_stopped_and_told() -> None:
    update = _message_update(STRANGER)
    with pytest.raises(ApplicationHandlerStop):
        await authorization_gate(update, _context())
    update.message.reply_text.assert_awaited_once()


async def test_stranger_callback_is_stopped_and_answered() -> None:
    update = _callback_update(STRANGER)
    with pytest.raises(ApplicationHandlerStop):
        await authorization_gate(update, _context())
    update.callback_query.answer.assert_awaited_once()


@pytest.mark.parametrize("text", ["/whoami", "/whoami@ParcelBot", "/WHOAMI extra"])
async def test_whoami_is_public(text: str) -> None:
    update = _message_update(STRANGER, text=text)
    await authorization_gate(update, _context())
    update.message.reply_text.assert_not_awaited()


async def test_update_without_user_is_stopped() -> None:
    update = _message_update(None)
    with pytest.raises(ApplicationHandlerStop):
        await authorization_gate(update, _context())
    update.message.reply_text.assert_not_awaited()


async def test_removed_db_user_is_no_longer_authorised() -> None:
    context = _context()
    assert await is_authorized(context, DB_ALLOWED)
    context.bot_data["user_repo"].get_allowed_user_ids = AsyncMock(return_value=[])
    assert not await is_authorized(context, DB_ALLOWED)


async def test_missing_config_and_repo_denies() -> None:
    assert not await is_authorized(SimpleNamespace(bot_data={}), OWNER)


def test_gate_registered_before_all_other_handlers() -> None:
    app = MagicMock()
    app.bot_data = {}
    register_handlers(
        app,
        config=MagicMock(),
        parcel_repo=MagicMock(),
        user_repo=MagicMock(),
        registry=MagicMock(),
    )
    gate_calls = [
        c
        for c in app.add_handler.call_args_list
        if isinstance(c.args[0], TypeHandler) and c.args[0].callback is authorization_gate
    ]
    assert len(gate_calls) == 1
    assert gate_calls[0].kwargs["group"] == AUTH_GATE_GROUP
    other_groups = [c.kwargs.get("group", 0) for c in app.add_handler.call_args_list[1:]]
    assert all(group > AUTH_GATE_GROUP for group in other_groups)
