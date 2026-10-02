"""Per-user cooldowns on /checkall and the manual refresh."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from parcel_tracker.bot import callbacks, parcel_commands, throttle
from parcel_tracker.db.models import Parcel


class _Clock:
    def __init__(self) -> None:
        self.t = 1000.0

    def __call__(self) -> float:
        return self.t


def test_cooldown_blocks_until_expiry() -> None:
    clock = _Clock()
    cd = throttle.Cooldown(60, clock=clock)
    assert cd.wait_seconds(1) == 0
    clock.t += 10
    assert cd.wait_seconds(1) == 50
    assert cd.wait_seconds(2) == 0  # other users unaffected
    clock.t += 50
    assert cd.wait_seconds(1) == 0


@pytest.fixture
def fresh_cooldowns(monkeypatch: pytest.MonkeyPatch) -> _Clock:
    clock = _Clock()
    monkeypatch.setattr(throttle, "CHECKALL", throttle.Cooldown(60, clock=clock))
    monkeypatch.setattr(throttle, "REFRESH", throttle.Cooldown(20, clock=clock))
    return clock


async def test_checkall_runs_once_per_cooldown(
    fresh_cooldowns: _Clock, monkeypatch: pytest.MonkeyPatch
) -> None:
    check = AsyncMock(return_value=3)
    monkeypatch.setitem(parcel_commands.__dict__, "check_user_now", check)
    reply = AsyncMock()
    upd = SimpleNamespace(
        effective_user=SimpleNamespace(id=7), effective_message=SimpleNamespace(reply_text=reply)
    )
    ctx = SimpleNamespace(bot_data={})
    await parcel_commands.cmd_checkall(upd, ctx)  # type: ignore[arg-type]
    await parcel_commands.cmd_checkall(upd, ctx)  # type: ignore[arg-type]
    assert check.await_count == 1
    assert "60" in reply.await_args.args[0]
    fresh_cooldowns.t += 61
    await parcel_commands.cmd_checkall(upd, ctx)  # type: ignore[arg-type]
    assert check.await_count == 2


async def test_refresh_runs_once_per_cooldown_and_keeps_the_card(
    fresh_cooldowns: _Clock, monkeypatch: pytest.MonkeyPatch
) -> None:
    check = AsyncMock(return_value="no_change")
    monkeypatch.setitem(callbacks.__dict__, "check_parcel_now", check)
    repo = AsyncMock()
    repo.get_for_user.return_value = Parcel(tracking_number="RR123456789DE", user_id=7)
    edit = AsyncMock()
    upd = SimpleNamespace(
        callback_query=SimpleNamespace(edit_message_text=edit),
        effective_user=SimpleNamespace(id=7),
    )
    ctx = SimpleNamespace(bot_data={"parcel_repo": repo})
    await callbacks._refresh_parcel(upd, ctx, "RR123456789DE")  # type: ignore[arg-type]
    await callbacks._refresh_parcel(upd, ctx, "RR123456789DE")  # type: ignore[arg-type]
    assert check.await_count == 1
    last_text = edit.await_args.args[0]
    assert "RR123456789DE" in last_text and "20" in last_text
