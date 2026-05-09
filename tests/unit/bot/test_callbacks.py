"""Smoke tests for callbacks.handle_callback dispatcher."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from parcel_tracker.bot.callbacks import handle_callback


@pytest.mark.asyncio
async def test_handle_callback_acks_and_edits() -> None:
    """handle_callback acks the query and edits the message with the action."""
    update = MagicMock()
    query = MagicMock()
    query.answer = AsyncMock()
    query.edit_message_text = AsyncMock()
    query.data = "list"
    update.callback_query = query
    context = MagicMock()

    await handle_callback(update, context)

    query.answer.assert_called_once()
    query.edit_message_text.assert_called_once()
    text = query.edit_message_text.call_args.args[0]
    assert "list" in text


@pytest.mark.asyncio
async def test_handle_callback_handles_payload() -> None:
    """Callback data with payload (action:payload) is split correctly."""
    update = MagicMock()
    query = MagicMock()
    query.answer = AsyncMock()
    query.edit_message_text = AsyncMock()
    query.data = "refresh:ABC123"
    update.callback_query = query
    context = MagicMock()

    await handle_callback(update, context)

    query.edit_message_text.assert_called_once()
    text = query.edit_message_text.call_args.args[0]
    assert "refresh" in text


@pytest.mark.asyncio
async def test_handle_callback_no_query_noop() -> None:
    """If callback_query is None, function returns early without raising."""
    update = MagicMock()
    update.callback_query = None
    context = MagicMock()
    # Must not raise
    await handle_callback(update, context)
