"""Owner and ADMIN_USER_IDS share one admin role across commands and buttons."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from parcel_tracker.bot import admin_commands, auth_commands, callbacks, health_commands

OWNER, ADMIN, USER = 1, 2, 3


def _ctx(**bot_data: object) -> SimpleNamespace:
    config = SimpleNamespace(owner_id=OWNER, admin_user_ids=frozenset({ADMIN}), allowed_user_ids=[])
    return SimpleNamespace(args=[], user_data={}, bot_data={"config": config, **bot_data})


def _update(uid: int) -> SimpleNamespace:
    reply = AsyncMock()
    msg = SimpleNamespace(reply_text=reply, chat_id=uid)
    return SimpleNamespace(
        effective_user=SimpleNamespace(id=uid),
        message=msg,
        effective_message=msg,
        callback_query=SimpleNamespace(edit_message_text=AsyncMock()),
    )


@pytest.mark.parametrize("uid", [OWNER, ADMIN])
def test_owner_and_admins_see_admin_menu(uid: int) -> None:
    assert callbacks._is_admin(_update(uid), _ctx()) is True  # type: ignore[arg-type]


def test_regular_user_is_not_admin() -> None:
    assert callbacks._is_admin(_update(USER), _ctx()) is False  # type: ignore[arg-type]


@pytest.mark.parametrize("uid", [OWNER, ADMIN])
async def test_admins_can_add_users_by_command(uid: int) -> None:
    users = AsyncMock()
    users.add_user.return_value = True
    ctx = _ctx(user_repo=users)
    ctx.args = ["42"]
    await auth_commands.cmd_adduser(_update(uid), ctx)  # type: ignore[arg-type]
    users.add_user.assert_awaited_once_with(user_id=42, added_by=uid)


async def test_regular_user_cannot_add_users() -> None:
    users = AsyncMock()
    ctx = _ctx(user_repo=users)
    ctx.args = ["42"]
    await auth_commands.cmd_adduser(_update(USER), ctx)  # type: ignore[arg-type]
    users.add_user.assert_not_awaited()


async def test_admin_stats_button_reaches_stats() -> None:
    repo = AsyncMock()
    repo.list_active_for_user.return_value = []
    repo.list_archived_for_user.return_value = []
    repo.count_events_for_user.return_value = 0
    health = AsyncMock()
    health.count_quarantined.return_value = 0
    users = AsyncMock()
    users.get_allowed_user_ids.return_value = []
    upd = _update(ADMIN)
    ctx = _ctx(parcel_repo=repo, health_repo=health, user_repo=users, registry=None)
    await admin_commands.cmd_stats(upd, ctx)  # type: ignore[arg-type]
    repo.list_active_for_user.assert_awaited_once()


async def test_owner_can_reset_tracker_health() -> None:
    health = AsyncMock()
    registry = SimpleNamespace(iter_all=lambda: [SimpleNamespace(name="dhl")])
    ctx = _ctx(health_repo=health, registry=registry)
    ctx.args = ["dhl"]
    await health_commands.cmd_health_reset(_update(OWNER), ctx)  # type: ignore[arg-type]
    health.reset_tracker.assert_awaited_once_with("dhl")
