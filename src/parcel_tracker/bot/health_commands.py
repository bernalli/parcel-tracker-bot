"""Telegram commands for tracker health: /health, /health <name>, /health reset <name>."""

from __future__ import annotations

import html
import logging
from datetime import UTC, datetime

from telegram import Update
from telegram.ext import ContextTypes

from parcel_tracker.bot.roles import is_admin
from parcel_tracker.i18n import _

logger = logging.getLogger(__name__)

_GREEN = "🟢"
_YELLOW = "🟡"
_RED = "🔴"

_THRESHOLD_GREEN = 0.95
_THRESHOLD_YELLOW = 0.80


def compute_color_emoji(*, success_rate: float, quarantine_until: datetime | None) -> str:
    """Return color emoji for a tracker based on success rate and quarantine state."""
    if quarantine_until is not None and quarantine_until > datetime.now(UTC):
        return _RED
    if success_rate >= _THRESHOLD_GREEN:
        return _GREEN
    if success_rate >= _THRESHOLD_YELLOW:
        return _YELLOW
    return _RED


async def cmd_health(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """`/health` — list all registered trackers with health badges."""
    reply_to = update.effective_message
    if reply_to is None:
        return
    registry = context.bot_data["registry"]
    health_repo = context.bot_data["health_repo"]

    lines = [_("📊 <b>Tracker Health</b> (last 24h aggregate)"), ""]
    for tracker in registry.iter_all():
        state = await health_repo.get_state(tracker.name, "")
        if state is None or state.total_checks == 0:
            lines.append(
                _("{emoji} <code>{name}</code> — no data yet").format(
                    emoji=_GREEN, name=tracker.name
                )
            )
            continue
        success_rate = (state.total_checks - state.total_failures) / state.total_checks
        emoji = compute_color_emoji(
            success_rate=success_rate, quarantine_until=state.quarantine_until
        )
        pct = round(success_rate * 100)
        quarantine_note = ""
        if state.quarantine_until and state.quarantine_until > datetime.now(UTC):
            until_short = state.quarantine_until.strftime("%H:%M UTC")
            quarantine_note = _(" — quarantined until {until}").format(until=until_short)
        lines.append(
            _("{emoji} <code>{name}</code> {pct}% — {checks} checks{note}").format(
                emoji=emoji,
                name=tracker.name,
                pct=pct,
                checks=state.total_checks,
                note=quarantine_note,
            )
        )

    lines.append("")
    lines.append(_("Use /health &lt;name&gt; for details."))
    text = "\n".join(lines)
    await reply_to.reply_text(text, parse_mode="HTML")


async def cmd_health_detail(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """`/health <name>` — show details for a single tracker."""
    if update.message is None:
        return
    if not context.args:
        await update.message.reply_text(_("Usage: /health <tracker_name>"))
        return
    name = context.args[0].lower()
    registry = context.bot_data["registry"]
    health_repo = context.bot_data["health_repo"]

    valid = {t.name for t in registry.iter_all()}
    if name not in valid:
        await update.message.reply_text(
            _("❌ Unknown tracker '{name}'. Use /health to see the list.").format(name=name)
        )
        return

    state = await health_repo.get_state(name, "")
    if state is None or state.total_checks == 0:
        await update.message.reply_text(
            _("📊 <b>{name}</b>\n\nNo data yet — tracker registered but never called.").format(
                name=html.escape(name)
            ),
            parse_mode="HTML",
        )
        return

    success_rate = (state.total_checks - state.total_failures) / state.total_checks
    emoji = compute_color_emoji(success_rate=success_rate, quarantine_until=state.quarantine_until)
    pct = round(success_rate * 100)
    last_success = state.last_success_at.isoformat(sep=" ") if state.last_success_at else "—"
    last_failure = state.last_failure_at.isoformat(sep=" ") if state.last_failure_at else "—"
    quarantine = state.quarantine_until.isoformat(sep=" ") if state.quarantine_until else "—"

    text = _(
        "📊 <b>{name}</b> health detail\n\n"
        "Status: {emoji} {pct}% success rate\n"
        "Last success: <code>{last_success}</code>\n"
        "Last failure: <code>{last_failure}</code>\n"
        "Consecutive failures: {consecutive}\n"
        "Quarantine until: <code>{quarantine}</code>\n"
        "Total checks: {checks}\n"
        "Total failures: {failures}"
    ).format(
        name=html.escape(name),
        emoji=emoji,
        pct=pct,
        last_success=last_success,
        last_failure=last_failure,
        consecutive=state.consecutive_failures,
        quarantine=quarantine,
        checks=state.total_checks,
        failures=state.total_failures,
    )
    await update.message.reply_text(text, parse_mode="HTML")


async def cmd_health_reset(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """`/health reset <name>` — admin-only manual reset for a tracker."""
    if update.message is None:
        return
    cfg = context.bot_data["config"]
    user_id = update.effective_user.id if update.effective_user else 0
    if not is_admin(cfg, user_id):
        await update.message.reply_text(_("❌ This command is admin-only."))
        return

    if not context.args:
        await update.message.reply_text(_("Usage: /health reset <tracker_name>"))
        return
    name = context.args[0].lower()
    registry = context.bot_data["registry"]
    valid = {t.name for t in registry.iter_all()}
    if name not in valid:
        await update.message.reply_text(
            _("❌ Unknown tracker '{name}'. Use /health to see the list.").format(name=name)
        )
        return
    health_repo = context.bot_data["health_repo"]
    await health_repo.reset_tracker(name)
    await update.message.reply_text(
        _(
            "✅ Reset done for tracker '<code>{name}</code>'.\nCleared counters and quarantine."
        ).format(name=html.escape(name)),
        parse_mode="HTML",
    )
