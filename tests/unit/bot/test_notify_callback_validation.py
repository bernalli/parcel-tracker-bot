from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

from parcel_tracker.bot import notify_commands


async def test_forged_status_is_not_persisted() -> None:
    repo = AsyncMock()
    query = SimpleNamespace(
        data="notify:junk" + "X" * 50,
        from_user=SimpleNamespace(id=6666),
        answer=AsyncMock(),
        edit_message_text=AsyncMock(),
    )
    await notify_commands.on_notify_callback(  # type: ignore[arg-type]
        SimpleNamespace(callback_query=query), SimpleNamespace(bot_data={"notification_repo": repo})
    )
    repo.set_pref.assert_not_awaited()


async def test_known_status_still_toggles() -> None:
    repo = AsyncMock()
    repo.get_pref.return_value = True
    repo.get_all_prefs.return_value = {}
    query = SimpleNamespace(
        data="notify:Delivered",
        from_user=SimpleNamespace(id=1),
        answer=AsyncMock(),
        edit_message_text=AsyncMock(),
    )
    await notify_commands.on_notify_callback(  # type: ignore[arg-type]
        SimpleNamespace(callback_query=query), SimpleNamespace(bot_data={"notification_repo": repo})
    )
    repo.set_pref.assert_awaited_once_with(user_id=1, status_value="Delivered", enabled=False)
