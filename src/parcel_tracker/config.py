"""Configuration loader: read .env into typed Config dataclass."""

from __future__ import annotations

import os
from dataclasses import dataclass, field

from dotenv import load_dotenv


class ConfigError(ValueError):
    """Raised when required configuration is missing or invalid."""


@dataclass(frozen=True, slots=True)
class Config:
    # Required
    telegram_bot_token: str
    owner_id: int

    # Optional / with defaults
    allowed_user_ids: list[int] = field(default_factory=list)
    check_interval_minutes: int = 30
    urgent_check_interval_minutes: int = 10
    max_consecutive_errors: int = 10
    auto_archive_hours: int = 48
    max_active_shipments: int = 20

    database_path: str = "/app/data/bot.db"

    log_level: str = "INFO"
    log_format: str = "json"
    log_full_tracking_id: bool = False

    default_language: str = "en"

    request_timeout: int = 30
    request_delay_min: int = 3
    request_delay_max: int = 8

    quarantine_3fail_hours: int = 1
    quarantine_6fail_hours: int = 6
    quarantine_12fail_hours: int = 24

    track17_api_key: str | None = None
    dhl_api_key: str | None = None
    ups_client_id: str | None = None
    ups_client_secret: str | None = None
    fedex_api_key: str | None = None
    fedex_secret_key: str | None = None

    metrics_enabled: bool = True
    metrics_bind_host: str = "0.0.0.0"  # noqa: S104 — Docker network scope; override via METRICS_BIND_HOST
    metrics_port: int = 9090

    @classmethod
    def from_env(cls, *, load_dotenv_file: bool = True) -> Config:
        """Build Config from environment variables (loads .env if present)."""
        if load_dotenv_file:
            load_dotenv()

        token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
        if not token:
            raise ConfigError("TELEGRAM_BOT_TOKEN is required (set in .env)")

        owner_raw = os.getenv("OWNER_ID", "").strip()
        if not owner_raw:
            raise ConfigError("OWNER_ID is required (Telegram user ID, integer)")
        try:
            owner_id = int(owner_raw)
        except ValueError as exc:
            raise ConfigError(f"OWNER_ID must be an integer, got: {owner_raw!r}") from exc

        allowed_raw = os.getenv("ALLOWED_USER_IDS", "")
        allowed: list[int] = []
        for token_id in allowed_raw.split(","):
            token_id = token_id.strip()
            if token_id:
                try:
                    allowed.append(int(token_id))
                except ValueError as exc:
                    raise ConfigError(
                        f"ALLOWED_USER_IDS contains non-integer: {token_id!r}"
                    ) from exc

        return cls(
            telegram_bot_token=token,
            owner_id=owner_id,
            allowed_user_ids=allowed,
            check_interval_minutes=_int_env("CHECK_INTERVAL_MINUTES", 30),
            urgent_check_interval_minutes=_int_env("URGENT_CHECK_INTERVAL_MINUTES", 10),
            max_consecutive_errors=_int_env("MAX_CONSECUTIVE_ERRORS", 10),
            auto_archive_hours=_int_env("AUTO_ARCHIVE_HOURS", 48),
            max_active_shipments=_int_env("MAX_ACTIVE_SHIPMENTS", 20),
            database_path=os.getenv("DATABASE_PATH", "/app/data/bot.db"),
            log_level=os.getenv("LOG_LEVEL", "INFO").upper(),
            log_format=os.getenv("LOG_FORMAT", "json").lower(),
            log_full_tracking_id=_bool_env("LOG_FULL_TRACKING_ID", False),
            default_language=os.getenv("DEFAULT_LANGUAGE", "en"),
            request_timeout=_int_env("REQUEST_TIMEOUT", 30),
            request_delay_min=_int_env("REQUEST_DELAY_MIN", 3),
            request_delay_max=_int_env("REQUEST_DELAY_MAX", 8),
            quarantine_3fail_hours=_int_env("QUARANTINE_3FAIL_HOURS", 1),
            quarantine_6fail_hours=_int_env("QUARANTINE_6FAIL_HOURS", 6),
            quarantine_12fail_hours=_int_env("QUARANTINE_12FAIL_HOURS", 24),
            track17_api_key=_optional_env("TRACK17_API_KEY"),
            dhl_api_key=_optional_env("DHL_API_KEY"),
            ups_client_id=_optional_env("UPS_CLIENT_ID"),
            ups_client_secret=_optional_env("UPS_CLIENT_SECRET"),
            fedex_api_key=_optional_env("FEDEX_API_KEY"),
            fedex_secret_key=_optional_env("FEDEX_SECRET_KEY"),
            metrics_enabled=_bool_env("METRICS_ENABLED", True),
            metrics_bind_host=os.getenv("METRICS_BIND_HOST", "0.0.0.0").strip() or "0.0.0.0",  # noqa: S104
            metrics_port=_int_env("METRICS_PORT", 9090),
        )


def _int_env(key: str, default: int) -> int:
    raw = os.getenv(key, "").strip()
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError as exc:
        raise ConfigError(f"{key} must be an integer, got: {raw!r}") from exc


def _bool_env(key: str, default: bool) -> bool:
    raw = os.getenv(key, "").strip().lower()
    if not raw:
        return default
    if raw in {"1", "true", "yes", "on"}:
        return True
    if raw in {"0", "false", "no", "off"}:
        return False
    raise ConfigError(f"{key} must be boolean (true/false), got: {raw!r}")


def _optional_env(key: str) -> str | None:
    raw = os.getenv(key, "").strip()
    return raw or None
