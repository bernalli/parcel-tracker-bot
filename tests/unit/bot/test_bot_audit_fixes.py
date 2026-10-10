"""Regression tests for the bot and tracker audit fixes."""

from __future__ import annotations

import time
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from parcel_tracker.bot import parcel_commands
from parcel_tracker.bot.auth_commands import revoke_user
from parcel_tracker.bot.pending import PENDING_TTL_S, pop_pending, set_pending
from parcel_tracker.core.detector import CourierDetector
from parcel_tracker.core.registry import TrackerRegistry
from parcel_tracker.db.migrations import init_schema
from parcel_tracker.db.models import Parcel, ShipmentStatus
from parcel_tracker.db.repository import ParcelRepository, UserRepository
from parcel_tracker.trackers import aramex, dhl, la_poste, ups


def _msg_update(text: str, user_id: int = 10) -> SimpleNamespace:
    return SimpleNamespace(
        effective_user=SimpleNamespace(id=user_id),
        effective_message=None,
        message=SimpleNamespace(text=text, reply_text=AsyncMock()),
    )


@pytest.mark.parametrize(
    "mapper",
    [ups.UpsTracker._map_status, dhl.DhlTracker._map_status, aramex.AramexTracker._map_status],
)
@pytest.mark.parametrize(
    "text", ["Not delivered - recipient absent", "Undelivered", "Could not be delivered"]
)
def test_scrapers_do_not_read_failed_delivery_as_delivered(mapper, text: str) -> None:
    assert mapper(text) is ShipmentStatus.UNDELIVERED


def test_french_negation_in_la_poste() -> None:
    assert la_poste.LaPosteTracker._map_status("Colis non livré") is ShipmentStatus.UNDELIVERED
    assert la_poste.LaPosteTracker._map_status("Votre colis est livré") is ShipmentStatus.DELIVERED


def test_fedex_number_is_not_routed_to_australia_post() -> None:
    from parcel_tracker.trackers.australia_post import AustraliaPostTracker

    assert not AustraliaPostTracker().detect("770123456789")
    assert not AustraliaPostTracker().detect("7712345678901234")


async def test_commands_accept_lowercase_and_spaced_codes(tmp_db_path) -> None:
    await init_schema(str(tmp_db_path))
    repo = ParcelRepository(str(tmp_db_path))
    await repo.create(Parcel(tracking_number="1Z999AA10123456784", user_id=10))
    update = SimpleNamespace(
        effective_user=SimpleNamespace(id=10),
        effective_message=SimpleNamespace(reply_text=AsyncMock()),
    )
    context = SimpleNamespace(args=["1z999aa1-0123-4567-84"], bot_data={"parcel_repo": repo})
    await parcel_commands.cmd_status(update, context)  # type: ignore[arg-type]
    text = update.effective_message.reply_text.await_args.args[0]
    assert not text.startswith("❌")  # the detail card, not "parcel not found"
    assert "<code>1Z999AA10123456784</code>" in text


async def test_product_name_at_name_prompt_is_a_name() -> None:
    repo = AsyncMock()
    repo.rename.return_value = True
    update = _msg_update("AirPods2023")
    context = SimpleNamespace(
        args=[],
        bot_data={"parcel_repo": repo, "detector": None},
        user_data={"pending": {"action": "name", "tn": "TN1"}},
    )
    await parcel_commands.handle_message(update, context)  # type: ignore[arg-type]
    repo.rename.assert_awaited_once()
    repo.create.assert_not_awaited()


async def test_pasted_code_at_rename_prompt_becomes_a_parcel() -> None:
    repo = AsyncMock()
    repo.create.return_value = object()
    update = _msg_update("RR123456785IT")
    context = SimpleNamespace(
        args=[],
        bot_data={"parcel_repo": repo, "detector": None},
        user_data={"pending": {"action": "rename", "tn": "TN1"}},
    )
    await parcel_commands.handle_message(update, context)  # type: ignore[arg-type]
    repo.rename.assert_not_awaited()
    repo.create.assert_awaited_once()


def test_pending_prompts_expire(monkeypatch) -> None:
    context = SimpleNamespace(user_data={})
    set_pending(context, "adduser")
    real = time.monotonic()
    monkeypatch.setattr(time, "monotonic", lambda: real + PENDING_TTL_S + 1)
    assert pop_pending(context) is None
    assert "pending" not in context.user_data


async def test_expired_adduser_prompt_does_not_authorise_a_pasted_number(monkeypatch) -> None:
    user_repo = AsyncMock()
    repo = AsyncMock()
    repo.create.return_value = None
    context = SimpleNamespace(
        args=[],
        bot_data={"parcel_repo": repo, "user_repo": user_repo, "detector": None},
        user_data={},
    )
    set_pending(context, "adduser")
    real = time.monotonic()
    monkeypatch.setattr(time, "monotonic", lambda: real + PENDING_TTL_S + 1)
    await parcel_commands.handle_message(_msg_update("1234567890"), context)  # type: ignore[arg-type]
    user_repo.add_user.assert_not_awaited()


@pytest.mark.parametrize("code", ["АБВГДЕЖЗИК", "ＡＢＣ１２３４５６７８é"])
async def test_non_ascii_codes_are_rejected(code: str) -> None:
    repo = AsyncMock()
    update = SimpleNamespace(
        effective_user=SimpleNamespace(id=10),
        message=SimpleNamespace(reply_text=AsyncMock()),
    )
    context = SimpleNamespace(args=[code], user_data={}, bot_data={"parcel_repo": repo})
    await parcel_commands.cmd_add(update, context)  # type: ignore[arg-type]
    repo.create.assert_not_awaited()


async def test_full_width_digits_are_folded_to_ascii() -> None:
    repo = AsyncMock()
    repo.create.return_value = Parcel(tracking_number="RR123456785IT", user_id=10, name="x")
    update = SimpleNamespace(
        effective_user=SimpleNamespace(id=10),
        message=SimpleNamespace(reply_text=AsyncMock()),
    )
    context = SimpleNamespace(
        args=["ＲＲ１２３４５６７８５ＩＴ", "x"], user_data={}, bot_data={"parcel_repo": repo}
    )
    await parcel_commands.cmd_add(update, context)  # type: ignore[arg-type]
    assert repo.create.await_args.args[0].tracking_number == "RR123456785IT"


async def test_admin_cannot_revoke_owner_or_wipe_unlisted_user(tmp_db_path) -> None:
    await init_schema(str(tmp_db_path))
    users = UserRepository(str(tmp_db_path))
    parcels = ParcelRepository(str(tmp_db_path))
    await parcels.create(Parcel(tracking_number="TN100001", user_id=1))
    await parcels.create(Parcel(tracking_number="TN100002", user_id=55))
    config = SimpleNamespace(owner_id=1, admin_user_ids=frozenset({7}), allowed_user_ids=[])
    context = SimpleNamespace(bot_data={"config": config, "user_repo": users})
    reply = await revoke_user(context, 1)  # type: ignore[arg-type]
    assert "configuration" in reply
    assert await parcels.get_for_user("TN100001", user_id=1) is not None
    reply = await revoke_user(context, 55)  # type: ignore[arg-type]
    assert "not in the authorised list" in reply
    assert await parcels.get_for_user("TN100002", user_id=55) is not None
    await users.add_user(user_id=55, added_by=7)
    await revoke_user(context, 55)  # type: ignore[arg-type]
    assert await parcels.get_for_user("TN100002", user_id=55) is None


def test_status_labels_are_translated() -> None:
    from parcel_tracker.bot.formatting import status_label
    from parcel_tracker.i18n import LOCALE_DIR, translator_for, using

    with using(translator_for("it", LOCALE_DIR)):
        assert status_label(ShipmentStatus.IN_TRANSIT) == "In transito"
        assert status_label(ShipmentStatus.DELIVERED) == "Consegnato"


async def test_long_text_echo_is_clipped() -> None:
    update = _msg_update("x" * 5000)
    context = SimpleNamespace(
        args=[], bot_data={"parcel_repo": AsyncMock(), "detector": None}, user_data={}
    )
    await parcel_commands.handle_message(update, context)  # type: ignore[arg-type]
    text = update.message.reply_text.await_args.args[0]
    assert len(text) < 200


async def test_multi_line_paste_adds_every_code(tmp_db_path) -> None:
    await init_schema(str(tmp_db_path))
    repo = ParcelRepository(str(tmp_db_path))
    await repo.create(Parcel(tracking_number="LX987654321CN", user_id=10))
    update = _msg_update("RR123456785IT mug\nLX987654321CN\n1Z999AA10123456784 lamp")
    context = SimpleNamespace(
        args=[],
        bot_data={"parcel_repo": repo, "detector": CourierDetector(TrackerRegistry())},
        user_data={},
    )
    await parcel_commands.handle_message(update, context)  # type: ignore[arg-type]
    stored = {p.tracking_number: p.name for p in await repo.list_active_for_user(user_id=10)}
    assert stored == {"RR123456785IT": "mug", "LX987654321CN": None, "1Z999AA10123456784": "lamp"}
    text = update.message.reply_text.await_args.args[0]
    assert "Added 2 parcels" in text
    assert "1 was already tracked" in text


async def test_lang_shows_configured_default(tmp_path: Path) -> None:
    from parcel_tracker.bot.lang_command import cmd_lang

    await init_schema(str(tmp_path / "db.sqlite"))
    users = UserRepository(str(tmp_path / "db.sqlite"))
    reply = AsyncMock()
    update = SimpleNamespace(
        effective_user=SimpleNamespace(id=3), effective_message=SimpleNamespace(reply_text=reply)
    )
    context = SimpleNamespace(
        args=[], bot_data={"user_repo": users, "config": SimpleNamespace(default_language="it")}
    )
    await cmd_lang(update, context)  # type: ignore[arg-type]
    assert "<code>it</code>" in reply.await_args.args[0]


async def test_health_detail_matches_mixed_case_plugin_names() -> None:
    from parcel_tracker.bot.health_commands import cmd_health_detail

    registry = MagicMock()
    registry.iter_all.return_value = [SimpleNamespace(name="AcmeExpress")]
    health_repo = AsyncMock()
    health_repo.get_state.return_value = None
    reply = AsyncMock()
    update = SimpleNamespace(
        effective_user=SimpleNamespace(id=1), message=SimpleNamespace(reply_text=reply)
    )
    context = SimpleNamespace(
        args=["acmeexpress"], bot_data={"registry": registry, "health_repo": health_repo}
    )
    await cmd_health_detail(update, context)  # type: ignore[arg-type]
    health_repo.get_state.assert_awaited_once_with("AcmeExpress", "")
