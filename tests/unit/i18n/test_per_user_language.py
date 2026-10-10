"""The UI language is per user: one user's choice never changes another's."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from parcel_tracker.bot import messages
from parcel_tracker.db.migrations import get_connection, init_schema
from parcel_tracker.db.repository import UserRepository
from parcel_tracker.i18n import current_translator
from parcel_tracker.i18n.build import compile_all

OWNER, ALICE, BOB = 1, 2, 3


@pytest.fixture
async def users(tmp_path: Path) -> UserRepository:
    assert compile_all() == 0
    db = str(tmp_path / "bot.db")
    await init_schema(db)
    repo = UserRepository(db)
    await repo.add_user(user_id=ALICE, added_by=OWNER)
    await repo.add_user(user_id=BOB, added_by=OWNER)
    return repo


async def _render_for(user_id: int, users: UserRepository) -> str:
    """Run the per-update language hook, then render a message as a handler would."""
    import asyncio

    from parcel_tracker.bot.language import apply_user_language

    async def _handler() -> str:
        update = SimpleNamespace(effective_user=SimpleNamespace(id=user_id))
        ctx = SimpleNamespace(
            bot_data={"user_repo": users, "config": SimpleNamespace(default_language="en")}
        )
        await apply_user_language(update, ctx)  # type: ignore[arg-type]
        return messages.unauthorized()

    return await asyncio.create_task(_handler())


async def test_one_users_choice_does_not_change_anothers(users: UserRepository) -> None:
    import asyncio

    from parcel_tracker.bot.lang_command import set_user_language

    # As the /lang handler does: inside the update's own task.
    await asyncio.create_task(set_user_language(users, ALICE, "it"))
    assert "Non sei autorizzato" in await _render_for(ALICE, users)
    assert "not authorised" in await _render_for(BOB, users)
    assert current_translator().locale == "en"  # nothing global changed


async def test_owner_language_is_persisted(users: UserRepository) -> None:
    await users.set_language(OWNER, "it")  # owner is not in allowed_users
    assert await users.get_language(OWNER) == "it"
    assert "Non sei autorizzato" in await _render_for(OWNER, users)


async def test_default_language_applies_without_a_choice(users: UserRepository) -> None:
    assert await users.get_language(BOB, default="it") == "it"
    assert await users.get_language(BOB) == "en"


async def test_notifications_use_the_recipients_language(users: UserRepository) -> None:
    from parcel_tracker.notifier.telegram import TelegramNotifier

    await users.set_language(ALICE, "it")
    bot = SimpleNamespace(send_message=AsyncMock(), send_photo=AsyncMock())
    notifier = TelegramNotifier(bot=bot, language_for=users.get_language)
    for uid in (ALICE, BOB):
        await notifier.send_delivery_confirmation(
            chat_id=uid, tracking_number="RR123456789DE", parcel_name=None, location=None
        )
    it_text, en_text = (c.kwargs["text"] for c in bot.send_message.await_args_list)
    assert it_text != en_text
    assert en_text == en_text.encode().decode()  # sanity
    assert current_translator().locale == "en"


async def test_erasing_a_user_drops_their_language(users: UserRepository, tmp_path: Path) -> None:
    await users.set_language(ALICE, "it")
    await users.remove_user(ALICE)
    async with get_connection(str(tmp_path / "bot.db")) as conn:
        cur = await conn.execute("SELECT COUNT(*) FROM user_language WHERE user_id = ?", (ALICE,))
        assert (await cur.fetchone())[0] == 0


async def test_erased_language_does_not_come_back_after_a_restart(
    users: UserRepository, tmp_path: Path
) -> None:
    db = str(tmp_path / "bot.db")
    await users.set_language(ALICE, "it")
    # A database written by an older version also holds the choice in allowed_users.
    async with get_connection(db) as conn:
        await conn.execute("UPDATE allowed_users SET language = 'it' WHERE user_id = ?", (ALICE,))
        await conn.commit()
    await users.erase_user_data(ALICE)
    assert await users.get_language(ALICE) == "en"
    await init_schema(db)  # startup migrations run again
    assert await users.get_language(ALICE) == "en"
