"""Dispatcher tests for parcel_tracker.bot.callbacks.

Covers:
  - nav:* prefixes edit the menu message with the right submenu
  - action:* prefixes invoke the corresponding cmd_*
  - prompt:* prefixes edit the message with prompt text + back keyboard
  - admin gates reject non-admins for action:users / nav:admin
  - main_menu(is_admin=...) exposes/hides the admin row
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from parcel_tracker.bot import callbacks
from parcel_tracker.bot.callbacks import handle_callback
from parcel_tracker.bot.keyboards import main_menu


def _make_update(callback_data: str, *, user_id: int = 42) -> MagicMock:
    update = MagicMock()
    query = MagicMock()
    query.answer = AsyncMock()
    query.edit_message_text = AsyncMock()
    query.data = callback_data
    update.callback_query = query
    update.effective_user = MagicMock()
    update.effective_user.id = user_id
    # PTB convention: when the update is a callback_query, effective_message
    # mirrors callback_query.message.
    update.effective_message = query.message
    update.effective_message.reply_text = AsyncMock()
    update.message = None
    return update


def _make_context(*, admin_ids: frozenset[int] = frozenset(), **bot_data: object) -> MagicMock:
    context = MagicMock()
    config = MagicMock()
    config.admin_user_ids = admin_ids
    context.bot_data = {"config": config, **bot_data}
    context.args = []
    return context


# ---------------------------------------------------------------------------
# nav:*
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_nav_main_edits_with_main_menu() -> None:
    update = _make_update("nav:main")
    context = _make_context()

    await handle_callback(update, context)

    update.callback_query.answer.assert_awaited_once()
    update.callback_query.edit_message_text.assert_awaited_once()
    kwargs = update.callback_query.edit_message_text.call_args.kwargs
    assert kwargs.get("reply_markup") is not None


@pytest.mark.asyncio
async def test_nav_parcels_edits_with_parcels_submenu() -> None:
    update = _make_update("nav:parcels")
    context = _make_context()

    await handle_callback(update, context)
    args = update.callback_query.edit_message_text.call_args
    text = args.args[0]
    assert "Parcels" in text or "Pacchi" in text


@pytest.mark.asyncio
async def test_nav_settings_edits_with_settings_submenu() -> None:
    update = _make_update("nav:settings")
    context = _make_context()

    await handle_callback(update, context)
    text = update.callback_query.edit_message_text.call_args.args[0]
    assert "Settings" in text or "Impostazioni" in text


@pytest.mark.asyncio
async def test_nav_advanced_edits_with_advanced_submenu() -> None:
    update = _make_update("nav:advanced")
    context = _make_context()

    await handle_callback(update, context)
    text = update.callback_query.edit_message_text.call_args.args[0]
    assert "Advanced" in text or "Avanzato" in text


@pytest.mark.asyncio
async def test_nav_admin_for_non_admin_rejects_with_unauthorized() -> None:
    update = _make_update("nav:admin", user_id=99)
    context = _make_context(admin_ids=frozenset({1, 2}))  # 99 is not admin

    await handle_callback(update, context)
    text = update.callback_query.edit_message_text.call_args.args[0]
    assert "authorised" in text.lower() or "autorizzato" in text.lower()


@pytest.mark.asyncio
async def test_nav_admin_for_admin_shows_admin_submenu() -> None:
    update = _make_update("nav:admin", user_id=1)
    context = _make_context(admin_ids=frozenset({1}))

    await handle_callback(update, context)
    text = update.callback_query.edit_message_text.call_args.args[0]
    assert "Admin" in text


# ---------------------------------------------------------------------------
# action:*
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_action_list_invokes_cmd_list() -> None:
    update = _make_update("action:list")
    context = _make_context()

    with patch.object(callbacks, "cmd_list", new=AsyncMock()) as mock_list:
        await handle_callback(update, context)

    mock_list.assert_awaited_once_with(update, context)


@pytest.mark.asyncio
async def test_action_help_invokes_cmd_help() -> None:
    update = _make_update("action:help")
    context = _make_context()

    with patch.object(callbacks, "cmd_help", new=AsyncMock()) as mock_help:
        await handle_callback(update, context)

    mock_help.assert_awaited_once_with(update, context)


@pytest.mark.asyncio
async def test_action_health_for_non_admin_still_works() -> None:
    """Tracker health is in advanced submenu — public, not admin-gated."""
    update = _make_update("action:health", user_id=99)
    context = _make_context(admin_ids=frozenset({1}))

    # Patch the lazy import target inside callbacks module
    with patch("parcel_tracker.bot.health_commands.cmd_health", new=AsyncMock()) as mock_health:
        await handle_callback(update, context)

    mock_health.assert_awaited_once_with(update, context)


@pytest.mark.asyncio
async def test_action_users_for_non_admin_rejected() -> None:
    """action:users is admin-only — non-admin sees unauthorised."""
    update = _make_update("action:users", user_id=99)
    context = _make_context(admin_ids=frozenset({1}))

    with patch.object(callbacks, "cmd_users", new=AsyncMock()) as mock_users:
        await handle_callback(update, context)

    mock_users.assert_not_called()
    text = update.callback_query.edit_message_text.call_args.args[0]
    assert "authorised" in text.lower() or "autorizzato" in text.lower()


@pytest.mark.asyncio
async def test_action_users_for_admin_invokes_cmd_users() -> None:
    update = _make_update("action:users", user_id=1)
    context = _make_context(admin_ids=frozenset({1}))

    with patch.object(callbacks, "cmd_users", new=AsyncMock()) as mock_users:
        await handle_callback(update, context)

    mock_users.assert_awaited_once_with(update, context)


@pytest.mark.asyncio
async def test_action_lang_clears_args_then_invokes_cmd_lang() -> None:
    update = _make_update("action:lang")
    context = _make_context()
    context.args = ["leftover"]  # Should be cleared before invocation

    with patch.object(callbacks, "cmd_lang", new=AsyncMock()) as mock_lang:
        await handle_callback(update, context)

    mock_lang.assert_awaited_once_with(update, context)
    assert context.args == []


# ---------------------------------------------------------------------------
# prompt:*
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_prompt_add_edits_with_prompt_text_and_back_keyboard() -> None:
    update = _make_update("prompt:add")
    context = _make_context()

    await handle_callback(update, context)
    args = update.callback_query.edit_message_text.call_args
    text = args.args[0]
    assert "/add" in text
    keyboard = args.kwargs["reply_markup"].inline_keyboard
    flat = [btn for row in keyboard for btn in row]
    # Single back button
    assert len(flat) == 1
    assert flat[0].callback_data == "nav:main"


@pytest.mark.asyncio
async def test_prompt_status_edits_with_prompt_text() -> None:
    update = _make_update("prompt:status")
    context = _make_context()

    await handle_callback(update, context)
    text = update.callback_query.edit_message_text.call_args.args[0]
    assert "/status" in text


@pytest.mark.asyncio
async def test_prompt_events_edits_with_prompt_text() -> None:
    update = _make_update("prompt:events")
    context = _make_context()

    await handle_callback(update, context)
    text = update.callback_query.edit_message_text.call_args.args[0]
    assert "/events" in text


@pytest.mark.asyncio
async def test_prompt_remove_edits_with_prompt_text() -> None:
    update = _make_update("prompt:remove")
    context = _make_context()

    await handle_callback(update, context)
    text = update.callback_query.edit_message_text.call_args.args[0]
    assert "/remove" in text


@pytest.mark.asyncio
async def test_prompt_rename_edits_with_prompt_text() -> None:
    update = _make_update("prompt:rename")
    context = _make_context()

    await handle_callback(update, context)
    text = update.callback_query.edit_message_text.call_args.args[0]
    assert "/rename" in text


# ---------------------------------------------------------------------------
# parcel:<action>:<tn>
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_parcel_refresh_invokes_cmd_status_with_tn_arg() -> None:
    update = _make_update("parcel:refresh:1Z999AA10123456784")
    context = _make_context()

    with patch.object(callbacks, "cmd_status", new=AsyncMock()) as mock_status:
        await handle_callback(update, context)

    mock_status.assert_awaited_once_with(update, context)
    assert context.args == ["1Z999AA10123456784"]


@pytest.mark.asyncio
async def test_parcel_remove_invokes_cmd_remove_with_tn_arg() -> None:
    update = _make_update("parcel:remove:ABC123")
    context = _make_context()

    with patch.object(callbacks, "cmd_remove", new=AsyncMock()) as mock_remove:
        await handle_callback(update, context)

    mock_remove.assert_awaited_once_with(update, context)
    assert context.args == ["ABC123"]


@pytest.mark.asyncio
async def test_parcel_events_invokes_cmd_events_with_tn_arg() -> None:
    update = _make_update("parcel:events:XYZ")
    context = _make_context()

    with patch.object(callbacks, "cmd_events", new=AsyncMock()) as mock_events:
        await handle_callback(update, context)

    mock_events.assert_awaited_once_with(update, context)
    assert context.args == ["XYZ"]


@pytest.mark.asyncio
async def test_parcel_unknown_action_is_noop() -> None:
    update = _make_update("parcel:bogus:ABC")
    context = _make_context()

    await handle_callback(update, context)
    update.callback_query.answer.assert_awaited_once()
    update.callback_query.edit_message_text.assert_not_called()


@pytest.mark.asyncio
async def test_parcel_malformed_callback_is_noop() -> None:
    """Missing tracking number → debug log, no crash."""
    update = _make_update("parcel:refresh")  # only two parts, missing tn
    context = _make_context()

    await handle_callback(update, context)
    update.callback_query.answer.assert_awaited_once()


# ---------------------------------------------------------------------------
# main_menu admin row visibility
# ---------------------------------------------------------------------------


def test_main_menu_with_is_admin_true_includes_admin_row() -> None:
    keyboard = main_menu(is_admin=True)
    flat = [btn for row in keyboard.inline_keyboard for btn in row]
    callback_datas = [b.callback_data for b in flat]
    assert "nav:admin" in callback_datas


def test_main_menu_with_is_admin_false_hides_admin_row() -> None:
    keyboard = main_menu(is_admin=False)
    flat = [btn for row in keyboard.inline_keyboard for btn in row]
    callback_datas = [b.callback_data for b in flat]
    assert "nav:admin" not in callback_datas
