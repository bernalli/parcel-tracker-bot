from __future__ import annotations

import subprocess
import sys
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from parcel_tracker.bot import callbacks
from parcel_tracker.core import scheduler as _sched
from parcel_tracker.db.models import Parcel, ShipmentStatus


def _cb_update(data: str, user_id: int = 10) -> SimpleNamespace:
    query = SimpleNamespace(
        data=data,
        answer=AsyncMock(),
        edit_message_text=AsyncMock(),
        from_user=SimpleNamespace(id=user_id),
    )
    return SimpleNamespace(
        callback_query=query,
        effective_user=SimpleNamespace(id=user_id),
    )


def _parcel() -> Parcel:
    return Parcel(
        tracking_number="TN1", user_id=10, name="iPhone", status=ShipmentStatus.IN_TRANSIT
    )


@pytest.mark.asyncio
async def test_refresh_fetches_live_and_edits_card() -> None:
    repo = AsyncMock()
    repo.get_for_user.return_value = _parcel()
    update = _cb_update("parcel:refresh:TN1")
    context = SimpleNamespace(bot_data={"parcel_repo": repo}, user_data={})
    # create=True: check_parcel_now is resolved via globals() inside _refresh_parcel
    # (lazy import to break the circular dependency), so it's not a top-level attribute.
    with patch.object(
        callbacks,
        "check_parcel_now",
        new=AsyncMock(return_value="updated"),
        create=True,
    ) as chk:
        await callbacks.handle_callback(update, context)  # type: ignore[arg-type]
    chk.assert_awaited_once_with(context.bot_data, user_id=10, tracking_number="TN1")
    # _edit passes the text as first positional arg of edit_message_text
    text = update.callback_query.edit_message_text.await_args.args[0]
    assert "iPhone" in text


@pytest.mark.asyncio
async def test_refresh_quarantined_prefixes_notice() -> None:
    repo = AsyncMock()
    repo.get_for_user.return_value = _parcel()
    update = _cb_update("parcel:refresh:TN1")
    context = SimpleNamespace(bot_data={"parcel_repo": repo}, user_data={})
    with patch.object(
        callbacks,
        "check_parcel_now",
        new=AsyncMock(return_value="quarantined"),
        create=True,
    ):
        await callbacks.handle_callback(update, context)  # type: ignore[arg-type]
    text = update.callback_query.edit_message_text.await_args.args[0]
    assert "⏳" in text  # avviso quarantena
    assert "iPhone" in text  # card dal DB comunque mostrata


@pytest.mark.asyncio
async def test_refresh_in_flight_guard_skips_second_tap() -> None:
    repo = AsyncMock()
    repo.get_for_user.return_value = _parcel()
    update = _cb_update("parcel:refresh:TN1")
    context = SimpleNamespace(bot_data={"parcel_repo": repo}, user_data={})
    callbacks._REFRESH_IN_FLIGHT.add("TN1")
    try:
        with patch.object(callbacks, "check_parcel_now", new=AsyncMock(), create=True) as chk:
            await callbacks.handle_callback(update, context)  # type: ignore[arg-type]
        chk.assert_not_awaited()
    finally:
        callbacks._REFRESH_IN_FLIGHT.discard("TN1")


@pytest.mark.asyncio
async def test_refresh_foreign_parcel_not_found() -> None:
    repo = AsyncMock()
    repo.get_for_user.return_value = None
    update = _cb_update("parcel:refresh:TN1")
    context = SimpleNamespace(bot_data={"parcel_repo": repo}, user_data={})
    with patch.object(callbacks, "check_parcel_now", new=AsyncMock(return_value=None), create=True):
        await callbacks.handle_callback(update, context)  # type: ignore[arg-type]
    text = update.callback_query.edit_message_text.await_args.args[0]
    assert "not found" in text.lower() or "❌" in text


# ---------------------------------------------------------------------------
# Production-path coverage: the branch where globals().get() falls back to
# scheduler.check_parcel_now (i.e. check_parcel_now NOT injected into
# callbacks' namespace).
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_refresh_resolves_to_scheduler_check_parcel_now_when_not_patched_on_callbacks() -> (
    None
):
    """Verifies the production fallback branch of globals().get().

    When `check_parcel_now` is NOT injected into the callbacks module
    namespace (no patch.object with create=True), _refresh_parcel must
    resolve to `scheduler.check_parcel_now` via the lazy import default.
    This test patches *scheduler.check_parcel_now* directly, confirming
    the real scheduler function is called — not a ghost attribute on callbacks.
    """
    # Ensure the key is absent from callbacks' globals (production state).
    assert "check_parcel_now" not in vars(callbacks), (
        "check_parcel_now should not be a top-level name in callbacks; "
        "if it is, the lazy-import guard is broken"
    )

    repo = AsyncMock()
    repo.get_for_user.return_value = _parcel()
    update = _cb_update("parcel:refresh:TN1")
    context = SimpleNamespace(bot_data={"parcel_repo": repo}, user_data={})

    # Patch the real function on the scheduler module (not on callbacks).
    with patch.object(_sched, "check_parcel_now", new=AsyncMock(return_value="updated")) as chk:
        await callbacks.handle_callback(update, context)  # type: ignore[arg-type]

    chk.assert_awaited_once_with(context.bot_data, user_id=10, tracking_number="TN1")
    text = update.callback_query.edit_message_text.await_args.args[0]
    assert "iPhone" in text


def test_no_circular_import_on_cold_import_of_scheduler() -> None:
    """Regression guard: importing scheduler in a fresh interpreter must not raise ImportError.

    A circular import between parcel_tracker.core.scheduler → notifier → bot
    → callbacks → scheduler would surface as an ImportError or AttributeError
    in a subprocess that has never touched any of those modules.
    """
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "import parcel_tracker.core.scheduler; "
                "import parcel_tracker.bot.callbacks; "
                "print('ok')"
            ),
        ],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, (
        f"Cold import raised an error (circular import regression?):\n"
        f"stdout: {result.stdout}\nstderr: {result.stderr}"
    )
    assert result.stdout.strip() == "ok"
