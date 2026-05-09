"""Smoke test: main module imports + Application builds without errors."""

from __future__ import annotations

import pytest


def test_main_module_imports() -> None:
    import parcel_tracker.main  # noqa: F401


@pytest.mark.asyncio
async def test_async_init_creates_db(
    tmp_path: pytest.TempPathFactory,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "fake")
    monkeypatch.setenv("OWNER_ID", "1")
    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "smoke.db"))

    from parcel_tracker.config import Config
    from parcel_tracker.main import build_bot_data

    config = Config.from_env(load_dotenv_file=False)
    bot_data = await build_bot_data(config)

    assert (tmp_path / "smoke.db").exists()
    assert bot_data["parcel_repo"] is not None
    assert len(list(bot_data["registry"].iter_all())) >= 1  # at least DHL built-in
