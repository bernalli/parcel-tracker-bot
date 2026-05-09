"""parcel-tracker-bot entry point."""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Any

from telegram import Update
from telegram.ext import Application, CallbackQueryHandler, CommandHandler, ContextTypes

from parcel_tracker.bot.handlers import register_handlers
from parcel_tracker.bot.health_commands import (
    cmd_health,
    cmd_health_detail,
    cmd_health_reset,
)
from parcel_tracker.bot.notify_commands import (
    cmd_notify_dispatch,
    on_notify_callback,
)
from parcel_tracker.config import Config
from parcel_tracker.core.detector import CourierDetector
from parcel_tracker.core.health import HealthManager, QuarantineThresholds
from parcel_tracker.core.rate_limiter import RateLimiter
from parcel_tracker.core.registry import TrackerRegistry
from parcel_tracker.db.health_repository import HealthRepository
from parcel_tracker.db.migrations import init_schema
from parcel_tracker.db.notification_repository import NotificationRepository
from parcel_tracker.db.repository import ParcelRepository, UserRepository
from parcel_tracker.i18n import Translator, set_default_translator
from parcel_tracker.notifier.preferences import CooldownConfig, NotificationPreferences
from parcel_tracker.notifier.telegram import TelegramNotifier
from parcel_tracker.observability.exporter import ExporterConfig, start_metrics_exporter
from parcel_tracker.observability.logging import configure_logging
from parcel_tracker.trackers import register_builtins

logger = logging.getLogger(__name__)


async def _health_dispatch(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Sub-command dispatcher for the /health command family.

    /health           → list all trackers (cmd_health)
    /health <name>    → tracker detail (cmd_health_detail)
    /health reset <name> → admin reset (cmd_health_reset, strips 'reset' arg)
    """
    args = context.args or []
    if not args:
        await cmd_health(update, context)
        return
    if args[0].lower() == "reset":
        context.args = args[1:]
        await cmd_health_reset(update, context)
        return
    await cmd_health_detail(update, context)


def _register_health_handlers(application: Application[Any, Any, Any, Any, Any, Any]) -> None:
    """Register /health command family with sub-command dispatch."""
    application.add_handler(CommandHandler("health", _health_dispatch))


def _register_notify_handlers(application: Application[Any, Any, Any, Any, Any, Any]) -> None:
    """Register /notify command and inline-button callback."""
    application.add_handler(CommandHandler("notify", cmd_notify_dispatch))
    application.add_handler(CallbackQueryHandler(on_notify_callback, pattern=r"^notify:"))


LOCALE_ROOT = Path(__file__).parent / "i18n" / "locale"


async def build_bot_data(config: Config) -> dict[str, Any]:
    """Assemble all bot dependencies into a dict suitable for application.bot_data.

    Note: TelegramNotifier requires application.bot which only exists after
    Application.builder().build(); the notifier is therefore wired in main()
    after this helper returns.
    """
    set_default_translator(Translator(locale=config.default_language, locale_dir=LOCALE_ROOT))
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
    detector = CourierDetector(registry)

    rate_limiter = RateLimiter(default_rate_per_min=config.rate_limit_default_per_min)
    for tracker_name, rate in config.rate_limit_overrides.items():
        rate_limiter.configure(tracker_name, rate)

    notification_repo = NotificationRepository(config.database_path)
    prefs = NotificationPreferences(
        repo=notification_repo,
        cooldown=CooldownConfig(minutes=config.notify_cooldown_minutes),
    )

    return {
        "config": config,
        "parcel_repo": parcel_repo,
        "user_repo": user_repo,
        "health_repo": health_repo,
        "registry": registry,
        "detector": detector,
        "health": health,
        "rate_limiter": rate_limiter,
        "notification_repo": notification_repo,
        "prefs": prefs,
        # NOTE: notifier added in main() after Application.builder().build()
    }


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

    bot_data = asyncio.run(build_bot_data(config))

    application = Application.builder().token(config.telegram_bot_token).build()

    notifier = TelegramNotifier(bot=application.bot)
    bot_data["notifier"] = notifier
    application.bot_data.update(bot_data)

    register_handlers(
        application,
        config=config,
        parcel_repo=bot_data["parcel_repo"],
        user_repo=bot_data["user_repo"],
        registry=bot_data["registry"],
    )
    _register_health_handlers(application)
    _register_notify_handlers(application)

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
