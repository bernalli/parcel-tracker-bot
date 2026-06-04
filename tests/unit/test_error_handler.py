"""Tests for the global PTB error handler (F0.8)."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from parcel_tracker.main import on_error


@pytest.mark.asyncio
async def test_on_error_replies_when_chat_present() -> None:
    update = MagicMock()
    update.effective_message = MagicMock()
    update.effective_message.reply_text = AsyncMock()
    context = MagicMock()
    context.error = RuntimeError("boom")
    await on_error(update, context)
    update.effective_message.reply_text.assert_awaited_once()


@pytest.mark.asyncio
async def test_on_error_no_message_does_not_raise() -> None:
    context = MagicMock()
    context.error = RuntimeError("boom")
    await on_error(None, context)  # must not raise
