from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

from parcel_tracker.bot import parcel_commands


def _update(text: str = "") -> SimpleNamespace:
    reply = AsyncMock()
    msg = SimpleNamespace(text=text, reply_text=reply)
    return SimpleNamespace(effective_user=SimpleNamespace(id=7), message=msg, effective_message=msg)


async def test_add_rejects_overlong_code() -> None:
    repo = AsyncMock()
    ctx = SimpleNamespace(args=["A1" * 2000], user_data={}, bot_data={"parcel_repo": repo})
    await parcel_commands.cmd_add(_update(), ctx)  # type: ignore[arg-type]
    repo.create.assert_not_awaited()


async def test_autoadd_rejects_overlong_code() -> None:
    repo = AsyncMock()
    upd = _update("RR" + "1" * 60 + "DE")
    ctx = SimpleNamespace(args=[], user_data={}, bot_data={"parcel_repo": repo, "detector": None})
    await parcel_commands.handle_message(upd, ctx)  # type: ignore[arg-type]
    repo.create.assert_not_awaited()


async def test_rename_command_caps_name() -> None:
    repo = AsyncMock()
    repo.rename.return_value = True
    ctx = SimpleNamespace(args=["RR123456789DE", "N" * 3500], bot_data={"parcel_repo": repo})
    await parcel_commands.cmd_rename(_update(), ctx)  # type: ignore[arg-type]
    assert len(repo.rename.await_args.kwargs["name"]) == 64


async def test_pending_rename_caps_name() -> None:
    repo = AsyncMock()
    repo.rename.return_value = True
    ctx = SimpleNamespace(
        args=[],
        bot_data={"parcel_repo": repo},
        user_data={"pending": {"action": "rename", "tn": "RR123456789DE"}},
    )
    await parcel_commands.handle_message(_update("N" * 3500), ctx)  # type: ignore[arg-type]
    assert len(repo.rename.await_args.kwargs["name"]) == 64
