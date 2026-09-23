"""Integration smoke: build_bot_data assembles the scheduler dependencies."""

from __future__ import annotations

from pathlib import Path

import pytest


@pytest.mark.asyncio
async def test_build_bot_data_includes_plan2_dependencies(tmp_path: Path) -> None:
    """build_bot_data must populate config + rate_limiter (with overrides applied)."""
    from parcel_tracker.config import Config
    from parcel_tracker.main import build_bot_data

    cfg = Config(
        telegram_bot_token="fake",  # noqa: S106
        owner_id=1,
        allowed_user_ids=[1],
        database_path=str(tmp_path / "t.db"),
        log_level="INFO",
        log_format="json",
        metrics_enabled=False,
        metrics_bind_host="127.0.0.1",
        metrics_port=19090,
        batch_size=5,
        rate_limit_default_per_min=10,
        rate_limit_overrides={"dhl": 60},
        notify_cooldown_minutes=60,
        admin_user_ids=frozenset({1}),
    )

    bot_data = await build_bot_data(cfg)

    assert "config" in bot_data
    assert bot_data["config"] is cfg
    assert "rate_limiter" in bot_data
    assert bot_data["rate_limiter"]._default_rate == 10
    # override applied via configure()
    assert "dhl" in bot_data["rate_limiter"]._buckets
    assert bot_data["rate_limiter"]._buckets["dhl"].capacity == 60
    # core deps present
    for key in ("parcel_repo", "user_repo", "health_repo", "registry", "detector", "health"):
        assert key in bot_data
    # notifier is intentionally NOT created in build_bot_data — it requires
    # application.bot which only exists post-Application.builder().build().
    assert "notifier" not in bot_data
    assert "prefs" in bot_data  # item 26 wired NotificationPreferences
    assert "notification_repo" in bot_data
