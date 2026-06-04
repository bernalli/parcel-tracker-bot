from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from parcel_tracker.bot import callbacks
from parcel_tracker.db.models import Parcel


def _query(data: str):
    return SimpleNamespace(
        data=data,
        answer=AsyncMock(),
        edit_message_text=AsyncMock(),
        from_user=SimpleNamespace(id=10),
        message=SimpleNamespace(reply_text=AsyncMock()),
    )


@pytest.mark.asyncio
async def test_nav_parcels_lists_parcels_as_picker(monkeypatch) -> None:
    repo = AsyncMock()
    repo.list_active_for_user.return_value = [Parcel(tracking_number="A", user_id=10)]
    q = _query("nav:parcels")
    update = SimpleNamespace(callback_query=q, effective_user=SimpleNamespace(id=10))
    context = SimpleNamespace(bot_data={"parcel_repo": repo, "config": SimpleNamespace(admin_user_ids=frozenset())}, user_data={})
    await callbacks.handle_callback(update, context)
    q.edit_message_text.assert_awaited()


@pytest.mark.asyncio
async def test_parcel_rename_sets_pending_and_prompts() -> None:
    q = _query("parcel:rename:A")
    update = SimpleNamespace(callback_query=q, effective_user=SimpleNamespace(id=10))
    context = SimpleNamespace(bot_data={"parcel_repo": AsyncMock()}, user_data={})
    await callbacks.handle_callback(update, context)
    assert context.user_data["pending"] == {"action": "rename", "tn": "A"}


@pytest.mark.asyncio
async def test_action_adduser_rejected_for_non_admin() -> None:
    """Security: a non-admin tapping/crafting action:adduser must be rejected and
    must NOT enter the authorise-user flow (no pending state set)."""
    q = _query("action:adduser")
    update = SimpleNamespace(callback_query=q, effective_user=SimpleNamespace(id=10))
    context = SimpleNamespace(
        bot_data={"config": SimpleNamespace(admin_user_ids=frozenset())}, user_data={}
    )
    await callbacks.handle_callback(update, context)
    assert "pending" not in context.user_data
    q.edit_message_text.assert_awaited()  # unauthorized message shown


@pytest.mark.asyncio
async def test_action_revoke_rejected_for_non_admin() -> None:
    """Security: a non-admin must not reach the revoke-user flow."""
    q = _query("action:revoke")
    update = SimpleNamespace(callback_query=q, effective_user=SimpleNamespace(id=10))
    context = SimpleNamespace(
        bot_data={"config": SimpleNamespace(admin_user_ids=frozenset())}, user_data={}
    )
    await callbacks.handle_callback(update, context)
    assert "pending" not in context.user_data


@pytest.mark.asyncio
async def test_parcel_map_renders_for_selected(monkeypatch) -> None:
    rendered = {}

    async def fake_map(update, context):
        rendered["called"] = context.args
    monkeypatch.setattr(callbacks, "cmd_map", fake_map)
    q = _query("parcel:map:A")
    update = SimpleNamespace(callback_query=q, effective_user=SimpleNamespace(id=10))
    context = SimpleNamespace(bot_data={}, user_data={})
    await callbacks.handle_callback(update, context)
    assert rendered["called"] == ["A"]
