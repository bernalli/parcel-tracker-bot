"""Telegram seller features: /web, CSV, share links, details, seller mode."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from parcel_tracker.bot import callbacks, parcel_commands, seller_commands
from parcel_tracker.db.migrations import init_schema
from parcel_tracker.db.models import Parcel
from parcel_tracker.db.repository import ParcelRepository
from parcel_tracker.db.settings_repository import SettingsRepository
from parcel_tracker.db.web_repository import WebRepository


@pytest.fixture
async def ctx(tmp_db_path):
    await init_schema(str(tmp_db_path))
    repo = ParcelRepository(str(tmp_db_path))
    await repo.create(Parcel(tracking_number="RR123456785IT", user_id=10, name="Mug"))
    config = SimpleNamespace(
        web_enabled=True, web_public_url="https://parcels.example", max_active_shipments=0
    )
    return SimpleNamespace(
        args=[],
        user_data={},
        bot_data={
            "parcel_repo": repo,
            "web_repo": WebRepository(str(tmp_db_path)),
            "settings": SettingsRepository(str(tmp_db_path)),
            "config": config,
        },
    )


def _msg_update(user_id: int = 10) -> SimpleNamespace:
    message = SimpleNamespace(reply_text=AsyncMock(), reply_document=AsyncMock())
    return SimpleNamespace(
        effective_user=SimpleNamespace(id=user_id), effective_message=message, message=message
    )


def _cb_update(data: str, user_id: int = 10) -> SimpleNamespace:
    query = SimpleNamespace(
        data=data,
        answer=AsyncMock(),
        edit_message_text=AsyncMock(),
        from_user=SimpleNamespace(id=user_id),
    )
    message = SimpleNamespace(reply_text=AsyncMock())
    return SimpleNamespace(
        callback_query=query,
        effective_user=SimpleNamespace(id=user_id),
        effective_message=message,
        message=None,
    )


async def test_web_sends_a_working_login_link(ctx) -> None:
    update = _msg_update()
    await seller_commands.cmd_web(update, ctx)  # type: ignore[arg-type]
    kwargs = update.message.reply_text.await_args.kwargs
    text = update.message.reply_text.await_args.args[0]
    assert kwargs["link_preview_options"].is_disabled
    assert "https://parcels.example/login?t=" in text
    token = text.split("login?t=")[1].split('"')[0]
    assert await ctx.bot_data["web_repo"].consume_login_token(token) == 10


async def test_web_disabled_explains_how_to_enable(ctx) -> None:
    ctx.bot_data["config"].web_enabled = False
    update = _msg_update()
    await seller_commands.cmd_web(update, ctx)  # type: ignore[arg-type]
    assert "WEB_ENABLED" in update.message.reply_text.await_args.args[0]


async def test_export_sends_csv(ctx) -> None:
    update = _msg_update()
    await seller_commands.cmd_export(update, ctx)  # type: ignore[arg-type]
    kwargs = update.message.reply_document.await_args.kwargs
    assert kwargs["filename"].endswith(".csv")
    body = kwargs["document"].getvalue().decode("utf-8-sig")
    assert "RR123456785IT,Mug" in body


async def test_export_with_nothing(ctx) -> None:
    update = _msg_update(user_id=77)
    await seller_commands.cmd_export(update, ctx)  # type: ignore[arg-type]
    update.message.reply_document.assert_not_awaited()


async def test_csv_document_is_imported(ctx) -> None:
    telegram_file = SimpleNamespace(
        download_as_bytearray=AsyncMock(
            return_value=bytearray(b"tracking,customer\nZZ12345678,Ada\n??,x\n")
        )
    )
    document = SimpleNamespace(file_size=40, get_file=AsyncMock(return_value=telegram_file))
    message = SimpleNamespace(document=document, reply_text=AsyncMock())
    update = SimpleNamespace(effective_user=SimpleNamespace(id=10), message=message)
    await seller_commands.handle_csv_document(update, ctx)  # type: ignore[arg-type]
    text = message.reply_text.await_args.args[0]
    assert "Added: 1" in text
    assert "invalid: 1" in text
    parcel = await ctx.bot_data["parcel_repo"].get_for_user("ZZ12345678", user_id=10)
    assert parcel is not None and parcel.recipient == "Ada"


async def test_csv_document_too_large(ctx) -> None:
    document = SimpleNamespace(file_size=50_000_000, get_file=AsyncMock())
    message = SimpleNamespace(document=document, reply_text=AsyncMock())
    update = SimpleNamespace(effective_user=SimpleNamespace(id=10), message=message)
    await seller_commands.handle_csv_document(update, ctx)  # type: ignore[arg-type]
    document.get_file.assert_not_awaited()


async def test_share_button_creates_one_stable_link(ctx) -> None:
    update = _cb_update("parcel:share:RR123456785IT")
    await callbacks.handle_callback(update, ctx)  # type: ignore[arg-type]
    first = update.effective_message.reply_text.await_args.args[0]
    assert "https://parcels.example/t/" in first
    await callbacks.handle_callback(update, ctx)  # type: ignore[arg-type]
    second = update.effective_message.reply_text.await_args.args[0]
    assert first == second


async def test_share_unknown_parcel(ctx) -> None:
    update = _cb_update("parcel:share:NOPE12345", user_id=10)
    await callbacks.handle_callback(update, ctx)  # type: ignore[arg-type]
    assert "not found" in update.effective_message.reply_text.await_args.args[0]


async def test_edit_detail_through_guided_input(ctx) -> None:
    update = _cb_update("detail:recipient:RR123456785IT")
    await callbacks.handle_callback(update, ctx)  # type: ignore[arg-type]
    assert ctx.user_data["pending"]["action"] == "detail"
    reply = AsyncMock()
    msg_update = SimpleNamespace(
        effective_user=SimpleNamespace(id=10),
        message=SimpleNamespace(text="Ada Lovelace", reply_text=reply),
    )
    ctx.bot_data["detector"] = None
    await parcel_commands.handle_message(msg_update, ctx)  # type: ignore[arg-type]
    parcel = await ctx.bot_data["parcel_repo"].get_for_user("RR123456785IT", user_id=10)
    assert parcel.recipient == "Ada Lovelace"
    assert "Ada Lovelace" in reply.await_args.args[0]
    # "-" clears the field
    await callbacks.handle_callback(update, ctx)  # type: ignore[arg-type]
    msg_update.message.text = "-"
    await parcel_commands.handle_message(msg_update, ctx)  # type: ignore[arg-type]
    parcel = await ctx.bot_data["parcel_repo"].get_for_user("RR123456785IT", user_id=10)
    assert parcel.recipient is None


async def test_tags_detail(ctx) -> None:
    pending = {"action": "detail", "field": "tags", "tn": "RR123456785IT"}
    reply_to = SimpleNamespace(reply_text=AsyncMock())
    await seller_commands.consume_detail(pending, "VIP, express", reply_to, ctx, 10)  # type: ignore[arg-type]
    parcel = await ctx.bot_data["parcel_repo"].get_for_user("RR123456785IT", user_id=10)
    assert parcel.tags == ["vip", "express"]


async def test_details_menu_and_unknown_field(ctx) -> None:
    update = _cb_update("parcel:details:RR123456785IT")
    await callbacks.handle_callback(update, ctx)  # type: ignore[arg-type]
    markup = update.callback_query.edit_message_text.await_args.kwargs["reply_markup"]
    datas = [b.callback_data for row in markup.inline_keyboard for b in row]
    assert "detail:notes:RR123456785IT" in datas
    assert all(len(d.encode()) <= 64 for d in datas)
    bad = _cb_update("detail:status:RR123456785IT")
    await callbacks.handle_callback(bad, ctx)  # type: ignore[arg-type]
    assert "pending" not in ctx.user_data


async def test_seller_mode_toggle(ctx) -> None:
    update = _cb_update("action:sellermode")
    await callbacks.handle_callback(update, ctx)  # type: ignore[arg-type]
    assert await ctx.bot_data["settings"].seller_mode(10)
    assert "Seller mode on" in update.callback_query.edit_message_text.await_args.args[0]
    await callbacks.handle_callback(update, ctx)  # type: ignore[arg-type]
    assert not await ctx.bot_data["settings"].seller_mode(10)


async def test_card_shows_seller_fields(ctx) -> None:
    from parcel_tracker.bot import messages

    repo = ctx.bot_data["parcel_repo"]
    await repo.update_details(
        "RR123456785IT", user_id=10, order_ref="#7", recipient="Ada", tags=["vip"], notes="ring"
    )
    card = messages.parcel_detail_card(await repo.get_for_user("RR123456785IT", user_id=10))
    for part in ("#7", "Ada", "#vip", "ring"):
        assert part in card


def test_parcel_keyboard_callback_data_fits() -> None:
    from parcel_tracker.bot.keyboards import parcel_actions_keyboard

    markup = parcel_actions_keyboard("A" * 40)
    for row in markup.inline_keyboard:
        for button in row:
            assert len(button.callback_data.encode()) <= 64


async def test_settings_menu_reflects_seller_mode(ctx) -> None:
    await ctx.bot_data["settings"].set_seller_mode(10, True)
    update = _cb_update("nav:settings")
    await callbacks.handle_callback(update, ctx)  # type: ignore[arg-type]
    markup = update.callback_query.edit_message_text.await_args.kwargs["reply_markup"]
    labels = [b.text for row in markup.inline_keyboard for b in row]
    assert any("Seller mode: on" in t for t in labels)


def test_handlers_register_seller_commands() -> None:
    from parcel_tracker.bot.handlers import register_handlers

    app = MagicMock()
    app.bot_data = {}
    register_handlers(
        app,
        config=MagicMock(),
        parcel_repo=MagicMock(),
        user_repo=MagicMock(),
        registry=MagicMock(),
    )
    commands = set()
    for call in app.add_handler.call_args_list:
        handler = call.args[0]
        commands |= set(getattr(handler, "commands", ()))
    assert {"web", "export"} <= commands
