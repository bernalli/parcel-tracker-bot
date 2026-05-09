"""Tests for src/parcel_tracker/config.py — env var loader."""

from __future__ import annotations

from collections.abc import Iterator

import pytest

from parcel_tracker.config import Config, ConfigError


@pytest.fixture
def env_clean(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Clear env vars that affect Config."""
    for key in [
        "TELEGRAM_BOT_TOKEN",
        "OWNER_ID",
        "ALLOWED_USER_IDS",
        "CHECK_INTERVAL_MINUTES",
        "DATABASE_PATH",
        "TRACK17_API_KEY",
    ]:
        monkeypatch.delenv(key, raising=False)
    yield


def test_missing_telegram_token_raises(env_clean: None) -> None:
    with pytest.raises(ConfigError, match="TELEGRAM_BOT_TOKEN"):
        Config.from_env()


def test_missing_owner_id_raises(monkeypatch: pytest.MonkeyPatch, env_clean: None) -> None:
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "fake")
    with pytest.raises(ConfigError, match="OWNER_ID"):
        Config.from_env()


def test_minimal_valid_config(monkeypatch: pytest.MonkeyPatch, env_clean: None) -> None:
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "fake_token")
    monkeypatch.setenv("OWNER_ID", "12345")

    cfg = Config.from_env()

    assert cfg.telegram_bot_token == "fake_token"
    assert cfg.owner_id == 12345
    assert cfg.allowed_user_ids == []
    assert cfg.check_interval_minutes == 30  # default
    assert cfg.database_path == "/app/data/bot.db"  # default
    assert cfg.track17_api_key is None  # optional


def test_allowed_user_ids_parses_csv(monkeypatch: pytest.MonkeyPatch, env_clean: None) -> None:
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "fake")
    monkeypatch.setenv("OWNER_ID", "1")
    monkeypatch.setenv("ALLOWED_USER_IDS", "111, 222 ,333")

    cfg = Config.from_env()

    assert cfg.allowed_user_ids == [111, 222, 333]


def test_quarantine_thresholds_parsed(monkeypatch: pytest.MonkeyPatch, env_clean: None) -> None:
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "fake")
    monkeypatch.setenv("OWNER_ID", "1")
    monkeypatch.setenv("QUARANTINE_3FAIL_HOURS", "2")

    cfg = Config.from_env()

    assert cfg.quarantine_3fail_hours == 2
    assert cfg.quarantine_6fail_hours == 6  # default
