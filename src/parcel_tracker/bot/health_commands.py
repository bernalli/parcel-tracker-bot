"""Telegram commands for tracker health: /health, /health <name>, /health reset <name>."""

from __future__ import annotations

import logging
from datetime import UTC, datetime

from telegram import Update
from telegram.ext import ContextTypes

logger = logging.getLogger(__name__)

_GREEN = "🟢"
_YELLOW = "🟡"
_RED = "🔴"


def compute_color_emoji(*, success_rate: float, quarantine_until: datetime | None) -> str:
    """Return color emoji for a tracker based on success rate and quarantine state."""
    if quarantine_until is not None and quarantine_until > datetime.now(UTC):
        return _RED
    if success_rate >= 0.95:
        return _GREEN
    if success_rate >= 0.80:
        return _YELLOW
    return _RED


async def cmd_health(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """`/health` — list all registered trackers with health badges."""
    if update.message is None:
        return
    registry = context.bot_data["registry"]
    health_repo = context.bot_data["health_repo"]

    lines = ["📊 <b>Tracker Health</b> (last 24h aggregate)", ""]
    for tracker in registry.iter_all():
        state = await health_repo.get_state(tracker.name, "")
        if state is None or state.total_checks == 0:
            lines.append(f"{_GREEN} <code>{tracker.name}</code> — no data yet")
            continue
        success_rate = (state.total_checks - state.total_failures) / state.total_checks
        emoji = compute_color_emoji(
            success_rate=success_rate, quarantine_until=state.quarantine_until
        )
        pct = round(success_rate * 100)
        quarantine_note = ""
        if state.quarantine_until and state.quarantine_until > datetime.now(UTC):
            until_short = state.quarantine_until.strftime("%H:%M UTC")
            quarantine_note = f" — quarantined until {until_short}"
        lines.append(
            f"{emoji} <code>{tracker.name}</code> "
            f"{pct}% — {state.total_checks} checks{quarantine_note}"
        )

    lines.append("")
    lines.append("Use /health &lt;name&gt; for details.")
    text = "\n".join(lines)
    await update.message.reply_text(text, parse_mode="HTML")


async def cmd_health_detail(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """`/health <name>` — show details for a single tracker."""
    if update.message is None:
        return
    if not context.args:
        await update.message.reply_text("Usage: /health <tracker_name>")
        return
    name = context.args[0].lower()
    registry = context.bot_data["registry"]
    health_repo = context.bot_data["health_repo"]

    valid = {t.name for t in registry.iter_all()}
    if name not in valid:
        await update.message.reply_text(
            f"❌ Unknown tracker '{name}'. Use /health to see the list."
        )
        return

    state = await health_repo.get_state(name, "")
    if state is None or state.total_checks == 0:
        await update.message.reply_text(
            f"📊 <b>{name}</b>\n\nNo data yet — tracker registered but never called.",
            parse_mode="HTML",
        )
        return

    success_rate = (state.total_checks - state.total_failures) / state.total_checks
    emoji = compute_color_emoji(success_rate=success_rate, quarantine_until=state.quarantine_until)
    pct = round(success_rate * 100)
    last_success = state.last_success_at.isoformat(sep=" ") if state.last_success_at else "—"
    last_failure = state.last_failure_at.isoformat(sep=" ") if state.last_failure_at else "—"
    quarantine = state.quarantine_until.isoformat(sep=" ") if state.quarantine_until else "—"

    text = (
        f"📊 <b>{name}</b> health detail\n\n"
        f"Status: {emoji} {pct}% success rate\n"
        f"Last success: <code>{last_success}</code>\n"
        f"Last failure: <code>{last_failure}</code>\n"
        f"Consecutive failures: {state.consecutive_failures}\n"
        f"Quarantine until: <code>{quarantine}</code>\n"
        f"Total checks: {state.total_checks}\n"
        f"Total failures: {state.total_failures}"
    )
    await update.message.reply_text(text, parse_mode="HTML")


async def cmd_health_reset(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """`/health reset <name>` — admin-only manual reset for a tracker."""
    if update.message is None:
        return
    cfg = context.bot_data["config"]
    user_id = update.effective_user.id if update.effective_user else 0
    admin_ids = cfg.admin_user_ids
    if user_id not in admin_ids:
        await update.message.reply_text("❌ This command is admin-only.")
        return

    if not context.args:
        await update.message.reply_text("Usage: /health reset <tracker_name>")
        return
    name = context.args[0].lower()
    health_repo = context.bot_data["health_repo"]
    await health_repo.reset_tracker(name)
    await update.message.reply_text(
        f"✅ Reset done for tracker '<code>{name}</code>'.\n" f"Cleared counters and quarantine.",
        parse_mode="HTML",
    )
