from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from parcel_tracker.bot import parcel_commands


def _ctx(repo: AsyncMock, args: list[str]) -> SimpleNamespace:
    return SimpleNamespace(args=args, bot_data={"parcel_repo": repo}, user_data={})


def _update(reply: AsyncMock) -> SimpleNamespace:
    return SimpleNamespace(
        effective_user=SimpleNamespace(id=10),
        message=SimpleNamespace(reply_text=reply),
    )


@pytest.mark.asyncio
async def test_add_multiword_name_joined() -> None:
    repo = AsyncMock()
    repo.create.return_value = object()
    reply = AsyncMock()
    await parcel_commands.cmd_add(_update(reply), _ctx(repo, ["TN12345678", "iPhone", "15", "Pro"]))  # type: ignore[arg-type]
    parcel = repo.create.await_args.args[0]
    assert parcel.name == "iPhone 15 Pro"
    assert parcel.carrier_code is None  # parametro posizionale carrier rimosso


@pytest.mark.asyncio
async def test_add_without_name_sets_pending_and_asks() -> None:
    repo = AsyncMock()
    repo.create.return_value = object()
    reply = AsyncMock()
    ctx = _ctx(repo, ["TN12345678"])
    await parcel_commands.cmd_add(_update(reply), ctx)  # type: ignore[arg-type]
    assert ctx.user_data["pending"] == {"action": "name", "tn": "TN12345678"}
    kwargs = reply.await_args.kwargs
    assert kwargs.get("reply_markup") is not None  # keyboard Skip presente


@pytest.mark.asyncio
async def test_add_with_name_does_not_prompt() -> None:
    repo = AsyncMock()
    repo.create.return_value = object()
    reply = AsyncMock()
    ctx = _ctx(repo, ["TN12345678", "scarpe"])
    await parcel_commands.cmd_add(_update(reply), ctx)  # type: ignore[arg-type]
    assert "pending" not in ctx.user_data


@pytest.mark.asyncio
async def test_add_name_truncated_to_64() -> None:
    repo = AsyncMock()
    repo.create.return_value = object()
    reply = AsyncMock()
    await parcel_commands.cmd_add(_update(reply), _ctx(repo, ["TN12345678", "x" * 200]))  # type: ignore[arg-type]
    parcel = repo.create.await_args.args[0]
    assert len(parcel.name) == 64
