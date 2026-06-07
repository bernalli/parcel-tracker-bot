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
    context = SimpleNamespace(
        bot_data={"parcel_repo": repo, "config": SimpleNamespace(admin_user_ids=frozenset())},
        user_data={},
    )
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


# --- open action: ownership-scoping (anti-IDOR) tests -----------------------


@pytest.mark.asyncio
async def test_parcel_open_shows_detail_card_for_owned_parcel() -> None:
    """Happy path: owned parcel -> detail card with <code>TN…</code> is shown."""
    repo = AsyncMock()
    repo.get_for_user = AsyncMock(
        return_value=Parcel(tracking_number="TN123", user_id=10, name="My Parcel")
    )
    q = _query("parcel:open:TN123")
    update = SimpleNamespace(callback_query=q, effective_user=SimpleNamespace(id=10))
    context = SimpleNamespace(bot_data={"parcel_repo": repo}, user_data={})
    await callbacks.handle_callback(update, context)
    repo.get_for_user.assert_awaited_once_with("TN123", user_id=10)
    q.edit_message_text.assert_awaited()
    text_sent = q.edit_message_text.await_args.args[0]
    assert "<code>TN123</code>" in text_sent


@pytest.mark.asyncio
async def test_parcel_open_not_found_shows_not_found_message() -> None:
    """If the parcel is not owned by the user, show not-found (no detail leaked)."""
    repo = AsyncMock()
    repo.get_for_user = AsyncMock(return_value=None)  # not owned / not existing
    q = _query("parcel:open:TN_OTHER")
    update = SimpleNamespace(callback_query=q, effective_user=SimpleNamespace(id=10))
    context = SimpleNamespace(bot_data={"parcel_repo": repo}, user_data={})
    await callbacks.handle_callback(update, context)
    repo.get_for_user.assert_awaited_once_with("TN_OTHER", user_id=10)
    q.edit_message_text.assert_awaited()
    text_sent = q.edit_message_text.await_args.args[0]
    # not-found message, not the detail card (same discriminating form as the IDOR test)
    assert "not found" in text_sent.lower()
    assert "Status:" not in text_sent  # detail card always has this; not_found never does


@pytest.mark.asyncio
async def test_parcel_open_idor_different_user_not_served() -> None:
    """IDOR: user 99 must not see a parcel owned by user 10 via open action."""
    repo = AsyncMock()
    repo.get_for_user = AsyncMock(return_value=None)  # ownership enforced: None for user 99
    q = _query("parcel:open:TN_USER10")
    update = SimpleNamespace(callback_query=q, effective_user=SimpleNamespace(id=99))
    context = SimpleNamespace(bot_data={"parcel_repo": repo}, user_data={})
    await callbacks.handle_callback(update, context)
    # Must query with the CALLER's user_id (99), not owner's (10)
    repo.get_for_user.assert_awaited_once_with("TN_USER10", user_id=99)
    # Must not expose the parcel detail card — only the "not found" message
    text_sent = q.edit_message_text.await_args.args[0]
    assert "not found" in text_sent.lower()  # not-found message was shown
    assert "Status:" not in text_sent  # detail card always has this; not_found never does
