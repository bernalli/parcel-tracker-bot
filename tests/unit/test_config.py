"""Tests for src/parcel_tracker/config.py — env var loader."""

from __future__ import annotations

import os
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
        "LOG_LEVEL",
        "LOG_FORMAT",
        "LOG_FULL_TRACKING_ID",
        "METRICS_ENABLED",
        "METRICS_BIND_HOST",
        "METRICS_PORT",
        "BATCH_SIZE",
        "RATE_LIMIT_DEFAULT_PER_MIN",
        "NOTIFY_COOLDOWN_MINUTES",
        "ADMIN_USER_IDS",
    ]:
        monkeypatch.delenv(key, raising=False)
    for key in [k for k in list(os.environ) if k.startswith("RATE_LIMIT_TRACKER_")]:
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


def test_config_loads_observability_defaults(
    monkeypatch: pytest.MonkeyPatch, env_clean: None
) -> None:
    """Phase 2 defaults: log_format=json, metrics_enabled=true, bind_host=0.0.0.0."""
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "fake")
    monkeypatch.setenv("OWNER_ID", "1")

    cfg = Config.from_env(load_dotenv_file=False)

    assert cfg.log_level == "INFO"
    assert cfg.log_format == "json"
    assert cfg.metrics_enabled is True
    assert cfg.metrics_bind_host == "0.0.0.0"  # noqa: S104
    assert cfg.metrics_port == 9090


def test_config_loads_observability_overrides(
    monkeypatch: pytest.MonkeyPatch, env_clean: None
) -> None:
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "fake")
    monkeypatch.setenv("OWNER_ID", "1")
    monkeypatch.setenv("LOG_LEVEL", "DEBUG")
    monkeypatch.setenv("LOG_FORMAT", "console")
    monkeypatch.setenv("METRICS_ENABLED", "false")
    monkeypatch.setenv("METRICS_BIND_HOST", "127.0.0.1")
    monkeypatch.setenv("METRICS_PORT", "19090")

    cfg = Config.from_env(load_dotenv_file=False)

    assert cfg.log_level == "DEBUG"
    assert cfg.log_format == "console"
    assert cfg.metrics_enabled is False
    assert cfg.metrics_bind_host == "127.0.0.1"
    assert cfg.metrics_port == 19090


def test_config_loads_scheduler_defaults(monkeypatch: pytest.MonkeyPatch, env_clean: None) -> None:
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "fake")  # noqa: S105
    monkeypatch.setenv("OWNER_ID", "1")
    cfg = Config.from_env(load_dotenv_file=False)
    assert cfg.batch_size == 10
    assert cfg.rate_limit_default_per_min == 10
    assert cfg.rate_limit_overrides == {}
    assert cfg.notify_cooldown_minutes == 60
    assert cfg.admin_user_ids == frozenset()


def test_config_loads_rate_limit_overrides(
    monkeypatch: pytest.MonkeyPatch, env_clean: None
) -> None:
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "fake")  # noqa: S105
    monkeypatch.setenv("OWNER_ID", "1")
    monkeypatch.setenv("RATE_LIMIT_TRACKER_TRACK17", "30")
    monkeypatch.setenv("RATE_LIMIT_TRACKER_DHL", "60")
    monkeypatch.setenv("BATCH_SIZE", "20")
    monkeypatch.setenv("ADMIN_USER_IDS", "111,222")
    monkeypatch.setenv("NOTIFY_COOLDOWN_MINUTES", "30")
    cfg = Config.from_env(load_dotenv_file=False)
    assert cfg.batch_size == 20
    assert cfg.rate_limit_overrides == {"track17": 30, "dhl": 60}
    assert cfg.admin_user_ids == frozenset({111, 222})
    assert cfg.notify_cooldown_minutes == 30


def test_config_admin_user_ids_invalid_raises_config_error(
    monkeypatch: pytest.MonkeyPatch, env_clean: None
) -> None:
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "fake")  # noqa: S105
    monkeypatch.setenv("OWNER_ID", "1")
    monkeypatch.setenv("ADMIN_USER_IDS", "abc,222")
    with pytest.raises(ConfigError, match="ADMIN_USER_IDS"):
        Config.from_env(load_dotenv_file=False)


def test_config_rate_limit_tracker_empty_name_raises_config_error(
    monkeypatch: pytest.MonkeyPatch, env_clean: None
) -> None:
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "fake")  # noqa: S105
    monkeypatch.setenv("OWNER_ID", "1")
    monkeypatch.setenv("RATE_LIMIT_TRACKER_", "5")
    with pytest.raises(ConfigError, match="tracker name"):
        Config.from_env(load_dotenv_file=False)
