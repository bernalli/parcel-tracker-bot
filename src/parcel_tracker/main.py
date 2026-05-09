"""parcel-tracker-bot entry point."""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path

from telegram.ext import Application

from parcel_tracker.bot.handlers import register_handlers
from parcel_tracker.config import Config
from parcel_tracker.core.detector import CourierDetector
from parcel_tracker.core.health import HealthManager, QuarantineThresholds
from parcel_tracker.core.registry import TrackerRegistry
from parcel_tracker.db.health_repository import HealthRepository
from parcel_tracker.db.migrations import init_schema
from parcel_tracker.db.repository import ParcelRepository, UserRepository
from parcel_tracker.notifier.telegram import TelegramNotifier
from parcel_tracker.observability.exporter import ExporterConfig, start_metrics_exporter
from parcel_tracker.observability.logging import configure_logging
from parcel_tracker.trackers import register_builtins

logger = logging.getLogger(__name__)


async def _async_init(
    config: Config,
) -> tuple[ParcelRepository, UserRepository, HealthManager, TrackerRegistry]:
    await init_schema(config.database_path)

    parcel_repo = ParcelRepository(config.database_path)
    user_repo = UserRepository(config.database_path)
    health_repo = HealthRepository(config.database_path)
    health = HealthManager(
        health_repo,
        thresholds=QuarantineThresholds(
            level1_failures=3,
            level1_hours=config.quarantine_3fail_hours,
            level2_failures=6,
            level2_hours=config.quarantine_6fail_hours,
            level3_failures=12,
            level3_hours=config.quarantine_12fail_hours,
        ),
    )

    registry = TrackerRegistry()
    register_builtins(registry, config)

    plugins_dir = Path(config.database_path).parent.parent / "plugins"
    if plugins_dir.exists():
        registry.load_from_directory(plugins_dir)

    return parcel_repo, user_repo, health, registry


def main() -> None:
    config = Config.from_env()

    configure_logging(log_level=config.log_level, log_format=config.log_format)
    start_metrics_exporter(
        ExporterConfig(
            enabled=config.metrics_enabled,
            host=config.metrics_bind_host,
            port=config.metrics_port,
        )
    )
    logger.info("Starting parcel-tracker-bot")

    parcel_repo, user_repo, health, registry = asyncio.run(_async_init(config))
    detector = CourierDetector(registry)

    application = Application.builder().token(config.telegram_bot_token).build()

    notifier = TelegramNotifier(bot=application.bot)

    application.bot_data["detector"] = detector
    application.bot_data["health"] = health
    application.bot_data["notifier"] = notifier
    application.bot_data["parcel_repo"] = parcel_repo
    application.bot_data["user_repo"] = user_repo
    application.bot_data["registry"] = registry

    register_handlers(
        application,
        config=config,
        parcel_repo=parcel_repo,
        user_repo=user_repo,
        registry=registry,
    )

    # Local import to avoid circular dependency at module level
    from parcel_tracker.core.scheduler import check_updates  # noqa: PLC0415

    assert application.job_queue is not None  # job-queue extra guarantees this
    application.job_queue.run_repeating(
        check_updates,
        interval=config.check_interval_minutes * 60,
        first=60,
        name="check_updates",
    )

    logger.info("Bot running (long polling)")
    application.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
