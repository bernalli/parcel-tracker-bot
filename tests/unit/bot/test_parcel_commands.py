"""Smoke tests for parcel_commands."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from parcel_tracker.bot import parcel_commands
from parcel_tracker.bot.parcel_commands import (
    cmd_add,
    cmd_events,
    cmd_list,
    cmd_remove,
    cmd_status,
    handle_message,
)
from parcel_tracker.db.models import Parcel, ShipmentStatus, TrackingEvent


def _make_update(text: str | None = None, args: list[str] | None = None) -> MagicMock:
    """Build a fully mocked Update with reply_text as AsyncMock."""
    update = MagicMock()
    update.message = MagicMock()
    update.message.reply_text = AsyncMock()
    update.message.text = text
    # PTB convention: effective_message mirrors message for command updates.
    update.effective_message = update.message
    update.effective_user = MagicMock()
    update.effective_user.id = 1
    return update


def _make_context(args: list[str] | None = None, **bot_data: object) -> MagicMock:
    context = MagicMock()
    context.args = args or []
    context.bot_data = dict(bot_data)
    context.user_data = {}  # no pending action
    return context


@pytest.mark.asyncio
async def test_cmd_list_empty() -> None:
    """cmd_list replies with NO_PARCELS_ACTIVE when repo returns []."""
    update = _make_update()
    repo = MagicMock(list_active_for_user=AsyncMock(return_value=[]))
    context = _make_context(parcel_repo=repo)

    await cmd_list(update, context)

    update.message.reply_text.assert_called_once()
    text = update.message.reply_text.call_args.args[0]
    assert "no active parcels" in text.lower()


@pytest.mark.asyncio
async def test_cmd_list_with_parcels() -> None:
    """cmd_list lists parcels when repo returns some."""
    update = _make_update()
    parcel = Parcel(tracking_number="ABC123", user_id=1, name="Camera")
    repo = MagicMock(list_active_for_user=AsyncMock(return_value=[parcel]))
    context = _make_context(parcel_repo=repo)

    await cmd_list(update, context)

    update.message.reply_text.assert_called_once()
    text = update.message.reply_text.call_args.args[0]
    assert "ABC123" in text
    assert "Camera" in text


@pytest.mark.asyncio
async def test_cmd_add_no_args_returns_usage() -> None:
    update = _make_update()
    context = _make_context(parcel_repo=MagicMock())
    await cmd_add(update, context)
    update.message.reply_text.assert_called_once()
    assert "/add" in update.message.reply_text.call_args.args[0]


@pytest.mark.asyncio
async def test_cmd_add_creates_parcel() -> None:
    update = _make_update()
    created_parcel = Parcel(tracking_number="XYZ", user_id=1, name="Mio pacco")
    repo = MagicMock(create=AsyncMock(return_value=created_parcel))
    context = _make_context(args=["XYZ", "Mio pacco"], parcel_repo=repo)
    await cmd_add(update, context)
    repo.create.assert_called_once()
    text = update.message.reply_text.call_args.args[0]
    assert "Mio pacco" in text


@pytest.mark.asyncio
async def test_cmd_status_not_found() -> None:
    update = _make_update()
    repo = MagicMock(get_for_user=AsyncMock(return_value=None))
    context = _make_context(args=["NOPE"], parcel_repo=repo)
    await cmd_status(update, context)
    text = update.message.reply_text.call_args.args[0]
    assert "not found" in text.lower()


@pytest.mark.asyncio
async def test_cmd_status_returns_details() -> None:
    parcel = Parcel(
        tracking_number="ABC",
        user_id=1,
        name="Test",
        carrier_name="DHL",
        status=ShipmentStatus.IN_TRANSIT,
    )
    update = _make_update()
    repo = MagicMock(get_for_user=AsyncMock(return_value=parcel))
    context = _make_context(args=["ABC"], parcel_repo=repo)
    await cmd_status(update, context)
    text = update.message.reply_text.call_args.args[0]
    assert "ABC" in text
    assert "DHL" in text


@pytest.mark.asyncio
async def test_cmd_events_empty() -> None:
    update = _make_update()
    owned = Parcel(tracking_number="ABC", user_id=1, status=ShipmentStatus.IN_TRANSIT)
    repo = MagicMock(
        get_for_user=AsyncMock(return_value=owned),
        get_history=AsyncMock(return_value=[]),
    )
    context = _make_context(args=["ABC"], parcel_repo=repo)
    await cmd_events(update, context)
    text = update.message.reply_text.call_args.args[0]
    assert "No events" in text


@pytest.mark.asyncio
async def test_cmd_events_lists_history() -> None:
    update = _make_update()
    owned = Parcel(tracking_number="ABC", user_id=1, status=ShipmentStatus.IN_TRANSIT)
    events = [TrackingEvent(time="2026-05-09", description="Picked up", location="Milan")]
    repo = MagicMock(
        get_for_user=AsyncMock(return_value=owned),
        get_history=AsyncMock(return_value=events),
    )
    context = _make_context(args=["ABC"], parcel_repo=repo)
    await cmd_events(update, context)
    text = update.message.reply_text.call_args.args[0]
    assert "Picked up" in text
    assert "Milan" in text


@pytest.mark.asyncio
async def test_cmd_remove_not_found() -> None:
    update = _make_update()
    repo = MagicMock(get_for_user=AsyncMock(return_value=None))
    context = _make_context(args=["MISSING"], parcel_repo=repo)
    await cmd_remove(update, context)
    text = update.message.reply_text.call_args.args[0]
    assert "not found" in text.lower()


@pytest.mark.asyncio
async def test_handle_message_echoes_hint() -> None:
    update = _make_update(text="ABC123")
    context = _make_context()
    await handle_message(update, context)
    text = update.message.reply_text.call_args.args[0]
    assert "/add ABC123" in text


@pytest.mark.asyncio
async def test_list_shows_name_first_with_code_aside() -> None:
    repo = AsyncMock()
    repo.list_active_for_user.return_value = [
        Parcel(tracking_number="TN1", user_id=10, name="iPhone 15"),
        Parcel(tracking_number="TN2", user_id=10),
    ]
    reply = AsyncMock()
    update = SimpleNamespace(
        effective_user=SimpleNamespace(id=10),
        effective_message=SimpleNamespace(reply_text=reply),
    )
    context = SimpleNamespace(args=[], bot_data={"parcel_repo": repo})
    await parcel_commands.cmd_list(update, context)  # type: ignore[arg-type]
    text = reply.await_args.args[0]
    line_named, line_unnamed = text.splitlines()
    assert line_named == "• <b>iPhone 15</b> — <code>TN1</code>"
    assert line_unnamed == "• <code>TN2</code>"


@pytest.mark.asyncio
async def test_history_shows_name_first_with_code_aside() -> None:
    repo = AsyncMock()
    repo.list_archived_for_user.return_value = [
        Parcel(tracking_number="TN1", user_id=10, name="scarpe"),
    ]
    reply = AsyncMock()
    update = SimpleNamespace(
        effective_user=SimpleNamespace(id=10),
        effective_message=SimpleNamespace(reply_text=reply),
    )
    context = SimpleNamespace(args=[], bot_data={"parcel_repo": repo})
    await parcel_commands.cmd_history(update, context)  # type: ignore[arg-type]
    text = reply.await_args.args[0]
    assert "✅ <b>scarpe</b> — <code>TN1</code>" in text


@pytest.mark.asyncio
async def test_events_formats_timestamps() -> None:
    repo = AsyncMock()
    repo.get_for_user.return_value = Parcel(tracking_number="TN1", user_id=10)
    repo.get_history.return_value = [
        TrackingEvent(time="2026-06-06T22:41:00+02:00", description="Arrived")
    ]
    reply = AsyncMock()
    update = SimpleNamespace(
        effective_user=SimpleNamespace(id=10),
        effective_message=SimpleNamespace(reply_text=reply),
    )
    context = SimpleNamespace(args=["TN1"], bot_data={"parcel_repo": repo})
    await parcel_commands.cmd_events(update, context)  # type: ignore[arg-type]
    text = reply.await_args.args[0]
    assert "06/06/2026 22:41" in text
    assert "2026-06-06T22:41" not in text
