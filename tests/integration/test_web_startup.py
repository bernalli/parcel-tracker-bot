"""The web dashboard starts and stops with the bot (real bot_data, real socket)."""

from __future__ import annotations

import socket
from types import SimpleNamespace

import aiohttp
import pytest


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


async def _bot_data(tmp_path, monkeypatch: pytest.MonkeyPatch, *, enabled: bool, port: int):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "fake")
    monkeypatch.setenv("OWNER_ID", "1")
    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "web.db"))
    monkeypatch.setenv("WEB_ENABLED", "true" if enabled else "false")
    monkeypatch.setenv("WEB_BIND_HOST", "127.0.0.1")
    monkeypatch.setenv("WEB_PORT", str(port))
    monkeypatch.setenv("MAPS_ENABLED", "false")
    from parcel_tracker.config import Config
    from parcel_tracker.main import build_bot_data

    return await build_bot_data(Config.from_env(load_dotenv_file=False))


async def test_dashboard_serves_while_the_bot_runs(tmp_path, monkeypatch) -> None:
    from parcel_tracker.main import _post_shutdown, _start_web

    port = _free_port()
    application = SimpleNamespace(
        bot_data=await _bot_data(tmp_path, monkeypatch, enabled=True, port=port)
    )
    await _start_web(application)  # type: ignore[arg-type]
    try:
        assert "web_server" in application.bot_data
        token = await application.bot_data["web_repo"].create_login_token(1)
        async with aiohttp.ClientSession(cookie_jar=aiohttp.CookieJar(unsafe=True)) as http:
            async with http.get(f"http://127.0.0.1:{port}/healthz") as resp:
                assert resp.status == 200
            async with http.post(
                f"http://127.0.0.1:{port}/login", data={"t": token}, allow_redirects=False
            ) as resp:
                assert resp.status == 303
            async with http.get(f"http://127.0.0.1:{port}/") as resp:
                assert resp.status == 200
                assert "Dashboard" in await resp.text()
    finally:
        await _post_shutdown(application)  # type: ignore[arg-type]
    with pytest.raises(OSError), socket.create_connection(("127.0.0.1", port), timeout=1):
        pass


async def test_disabled_dashboard_does_not_listen(tmp_path, monkeypatch) -> None:
    from parcel_tracker.main import _start_web

    port = _free_port()
    application = SimpleNamespace(
        bot_data=await _bot_data(tmp_path, monkeypatch, enabled=False, port=port)
    )
    await _start_web(application)  # type: ignore[arg-type]
    assert "web_server" not in application.bot_data


async def test_port_in_use_does_not_stop_the_bot(tmp_path, monkeypatch) -> None:
    from parcel_tracker.main import _start_web

    with socket.socket() as busy:
        busy.bind(("127.0.0.1", 0))
        busy.listen()
        port = int(busy.getsockname()[1])
        application = SimpleNamespace(
            bot_data=await _bot_data(tmp_path, monkeypatch, enabled=True, port=port)
        )
        await _start_web(application)  # type: ignore[arg-type]
    assert "web_server" not in application.bot_data
