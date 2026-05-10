"""Smoke tests for callbacks.handle_callback dispatcher entry point."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from parcel_tracker.bot.callbacks import handle_callback


@pytest.mark.asyncio
async def test_handle_callback_acks_unknown_prefix() -> None:
    """Unknown prefix → ack only, no edit."""
    update = MagicMock()
    query = MagicMock()
    query.answer = AsyncMock()
    query.edit_message_text = AsyncMock()
    query.data = "totally_unknown:foo"
    update.callback_query = query
    context = MagicMock()
    context.bot_data = {"config": MagicMock(admin_user_ids=frozenset())}

    await handle_callback(update, context)

    query.answer.assert_called_once()
    query.edit_message_text.assert_not_called()


@pytest.mark.asyncio
async def test_handle_callback_no_query_noop() -> None:
    """If callback_query is None, function returns early without raising."""
    update = MagicMock()
    update.callback_query = None
    context = MagicMock()
    # Must not raise
    await handle_callback(update, context)
