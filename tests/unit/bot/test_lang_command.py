from unittest.mock import AsyncMock, MagicMock

import pytest

from parcel_tracker.bot.lang_command import cmd_lang


@pytest.mark.asyncio
async def test_lang_no_args_shows_current(tmp_user_repo) -> None:
    repo = tmp_user_repo
    await repo.set_language(123, "it")
    update = MagicMock()
    update.message = AsyncMock()
    # PTB convention: effective_message mirrors message for command updates.
    update.effective_message = update.message
    update.effective_user = MagicMock(id=123)
    context = MagicMock()
    context.args = []
    context.bot_data = {"user_repo": repo}

    await cmd_lang(update, context)
    update.message.reply_text.assert_called_once()
    text = update.message.reply_text.call_args[0][0]
    assert "it" in text


@pytest.mark.asyncio
async def test_lang_invalid_locale(tmp_user_repo) -> None:
    update = MagicMock()
    update.message = AsyncMock()
    update.effective_message = update.message
    update.effective_user = MagicMock(id=123)
    context = MagicMock()
    context.args = ["xx"]
    context.bot_data = {"user_repo": tmp_user_repo}

    await cmd_lang(update, context)
    text = update.message.reply_text.call_args[0][0]
    assert "xx" in text
    assert "not available" in text or "non è disponibile" in text


@pytest.mark.asyncio
async def test_lang_switches_to_it(tmp_user_repo) -> None:
    update = MagicMock()
    update.message = AsyncMock()
    update.effective_message = update.message
    update.effective_user = MagicMock(id=123)
    context = MagicMock()
    context.args = ["it"]
    context.bot_data = {"user_repo": tmp_user_repo}

    await cmd_lang(update, context)
    assert await tmp_user_repo.get_language(123) == "it"
