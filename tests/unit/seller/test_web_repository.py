"""Login links, sessions and API tokens."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from parcel_tracker.db.migrations import init_schema
from parcel_tracker.db.settings_repository import SettingsRepository
from parcel_tracker.db.web_repository import LOGIN_TOKEN_TTL, WebRepository, digest

NOW = datetime(2026, 10, 1, 12, 0, tzinfo=UTC)


async def _web(path) -> WebRepository:
    await init_schema(str(path))
    return WebRepository(str(path))


async def test_login_token_is_single_use(tmp_db_path) -> None:
    web = await _web(tmp_db_path)
    token = await web.create_login_token(7, now=NOW)
    assert await web.consume_login_token(token, now=NOW) == 7
    assert await web.consume_login_token(token, now=NOW) is None


async def test_login_token_expires(tmp_db_path) -> None:
    web = await _web(tmp_db_path)
    token = await web.create_login_token(7, now=NOW)
    later = NOW + LOGIN_TOKEN_TTL + timedelta(seconds=1)
    assert await web.consume_login_token(token, now=later) is None


async def test_unknown_login_token(tmp_db_path) -> None:
    web = await _web(tmp_db_path)
    assert await web.consume_login_token("nope", now=NOW) is None


async def test_session_lifecycle(tmp_db_path) -> None:
    web = await _web(tmp_db_path)
    sid = await web.create_session(7, lifetime=timedelta(days=30), now=NOW)
    session = await web.get_session(sid, now=NOW + timedelta(days=1))
    assert session is not None
    assert session.user_id == 7
    assert session.csrf_token
    assert await web.get_session(sid, now=NOW + timedelta(days=31)) is None
    await web.delete_session(sid)
    assert await web.get_session(sid, now=NOW) is None


async def test_logout_everywhere(tmp_db_path) -> None:
    web = await _web(tmp_db_path)
    a = await web.create_session(7, lifetime=timedelta(days=1), now=NOW)
    b = await web.create_session(7, lifetime=timedelta(days=1), now=NOW)
    other = await web.create_session(8, lifetime=timedelta(days=1), now=NOW)
    assert await web.delete_sessions_for_user(7) == 2
    assert await web.get_session(a, now=NOW) is None
    assert await web.get_session(b, now=NOW) is None
    assert await web.get_session(other, now=NOW) is not None


async def test_api_tokens(tmp_db_path) -> None:
    web = await _web(tmp_db_path)
    token = await web.create_api_token(7, "woocommerce")
    assert token is not None
    assert token.startswith("ptb_")
    assert await web.user_for_api_token(token, now=NOW) == 7
    assert await web.user_for_api_token("ptb_wrong") is None
    assert await web.user_for_api_token("no-prefix") is None
    tokens = await web.list_api_tokens(7)
    assert [t.name for t in tokens] == ["woocommerce"]
    assert tokens[0].last_used_at == "2026-10-01 12:00:00"
    assert not await web.revoke_api_token(8, tokens[0].id)
    assert await web.revoke_api_token(7, tokens[0].id)
    assert await web.user_for_api_token(token) is None


async def test_api_token_cap(tmp_db_path) -> None:
    web = await _web(tmp_db_path)
    for i in range(20):
        assert await web.create_api_token(7, f"t{i}") is not None
    assert await web.create_api_token(7, "one too many") is None


def test_only_digests_are_stored() -> None:
    assert digest("abc") != "abc"
    assert len(digest("abc")) == 64


async def test_settings_repository(tmp_db_path) -> None:
    await init_schema(str(tmp_db_path))
    repo = SettingsRepository(str(tmp_db_path))
    assert not await repo.seller_mode(1)
    await repo.set_seller_mode(1, True)
    assert await repo.seller_mode(1)
    await repo.set_seller_mode(1, False)
    assert not await repo.seller_mode(1)
    await repo.set_user(1, "shop_name", "Bottega")
    assert await repo.shop_name(1) == "Bottega"
    await repo.set_user(1, "shop_name", "")
    assert await repo.shop_name(1) is None
    secret = await repo.get_or_create_secret("k")
    assert secret == await repo.get_or_create_secret("k")
    assert await repo.get_app("k") == secret
    assert await repo.get_app("missing") is None
