from __future__ import annotations

import pytest

from parcel_tracker.bot import messages

PAYLOAD = '<a href="https://example.invalid">x</a>'


@pytest.mark.parametrize(
    "render",
    [
        messages.to_add_use,
        messages.parcel_not_found,
        messages.parcel_duplicate,
        messages.parcel_removed,
        messages.no_events,
        messages.events_for,
        lambda v: messages.lang_not_supported(v, ["en", "it"]),
    ],
)
def test_user_input_is_escaped(render) -> None:  # type: ignore[no-untyped-def]
    out = render(PAYLOAD)
    assert PAYLOAD not in out
    assert "&lt;a href" in out


async def test_stats_escapes_carrier_names_from_carrier_data() -> None:
    from types import SimpleNamespace
    from unittest.mock import AsyncMock

    from parcel_tracker.bot import admin_commands
    from parcel_tracker.db.models import Parcel

    reply = AsyncMock()
    repo = AsyncMock()
    repo.list_active_for_user.return_value = [
        Parcel(tracking_number="RR123456789DE", user_id=1, carrier_name="<b>Evil</b>")
    ]
    repo.list_archived_for_user.return_value = []
    repo.count_events_for_user.return_value = 0
    health = AsyncMock()
    health.count_quarantined.return_value = 0
    users = AsyncMock()
    users.get_allowed_user_ids.return_value = []
    upd = SimpleNamespace(
        effective_user=SimpleNamespace(id=1), effective_message=SimpleNamespace(reply_text=reply)
    )
    ctx = SimpleNamespace(
        bot_data={
            "config": SimpleNamespace(owner_id=1, allowed_user_ids=[]),
            "parcel_repo": repo,
            "health_repo": health,
            "user_repo": users,
            "registry": None,
        }
    )
    await admin_commands.cmd_stats(upd, ctx)  # type: ignore[arg-type]
    assert "<b>Evil</b>" not in reply.await_args.args[0]
