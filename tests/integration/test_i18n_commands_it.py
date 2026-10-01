"""/notify and /health reply in the active language."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from parcel_tracker.bot import health_commands, notify_commands
from parcel_tracker.i18n import Translator, set_default_translator
from parcel_tracker.i18n.build import compile_all

LOCALE = Path(__file__).resolve().parents[2] / "src" / "parcel_tracker" / "i18n" / "locale"


@pytest.fixture
def italian() -> None:
    assert compile_all() == 0
    set_default_translator(Translator(locale="it", locale_dir=LOCALE))


@pytest.mark.asyncio
@pytest.mark.usefixtures("italian")
async def test_notify_menu_in_italian() -> None:
    reply = AsyncMock()
    repo = AsyncMock()
    repo.get_all_prefs.return_value = {}
    update = SimpleNamespace(
        effective_message=SimpleNamespace(reply_text=reply),
        effective_user=SimpleNamespace(id=1),
    )
    ctx = SimpleNamespace(args=[], bot_data={"notification_repo": repo})
    await notify_commands.cmd_notify_dispatch(update, ctx)  # type: ignore[arg-type]
    text = reply.await_args.args[0]
    assert "Preferenze di notifica" in text


@pytest.mark.asyncio
@pytest.mark.usefixtures("italian")
async def test_notify_all_and_none_in_italian() -> None:
    reply = AsyncMock()
    repo = AsyncMock()
    update = SimpleNamespace(
        effective_message=SimpleNamespace(reply_text=reply),
        effective_user=SimpleNamespace(id=1),
    )
    await notify_commands.cmd_notify_dispatch(  # type: ignore[arg-type]
        update, SimpleNamespace(args=["all"], bot_data={"notification_repo": repo})
    )
    assert "attivate" in reply.await_args.args[0]
    await notify_commands.cmd_notify_dispatch(  # type: ignore[arg-type]
        update, SimpleNamespace(args=["none"], bot_data={"notification_repo": repo})
    )
    assert "disattivate" in reply.await_args.args[0]


@pytest.mark.asyncio
@pytest.mark.usefixtures("italian")
async def test_health_reset_admin_only_in_italian() -> None:
    reply = AsyncMock()
    update = SimpleNamespace(
        message=SimpleNamespace(reply_text=reply),
        effective_user=SimpleNamespace(id=99),
    )
    ctx = SimpleNamespace(
        args=["dhl"], bot_data={"config": SimpleNamespace(admin_user_ids=frozenset())}
    )
    await health_commands.cmd_health_reset(update, ctx)  # type: ignore[arg-type]
    assert "amministratori" in reply.await_args.args[0]
