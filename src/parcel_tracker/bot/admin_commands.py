"""Admin commands: clean, cleanall, delivered, stats."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from parcel_tracker.bot import messages

if TYPE_CHECKING:
    from telegram import Update
    from telegram.ext import ContextTypes

logger = logging.getLogger(__name__)


def _is_owner(context: Any, user_id: int) -> bool:
    config = context.bot_data.get("config")
    if config is None:
        return False
    return bool(getattr(config, "owner_id", None) == user_id)


async def cmd_clean(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Clean delivered/expired parcels (owner only)."""
    user = update.effective_user
    reply_to = update.effective_message
    if user is None or reply_to is None:
        return
    if not _is_owner(context, user.id):
        await reply_to.reply_text(messages.owner_only(), parse_mode="HTML")
        return
    repo = context.bot_data["parcel_repo"]
    await repo.archive_delivered_for_user(user_id=user.id)
    await reply_to.reply_text(messages.clean_done(), parse_mode="HTML")


async def cmd_cleanall(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Remove all parcels (owner only — DANGEROUS)."""
    user = update.effective_user
    reply_to = update.effective_message
    if user is None or reply_to is None:
        return
    if not _is_owner(context, user.id):
        await reply_to.reply_text(messages.owner_only(), parse_mode="HTML")
        return
    repo = context.bot_data["parcel_repo"]
    await repo.archive_delivered_for_user(user_id=user.id)
    await reply_to.reply_text(messages.cleanall_done(), parse_mode="HTML")


async def cmd_delivered(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show delivered parcels (active + archived) for the user."""
    user = update.effective_user
    reply_to = update.effective_message
    if user is None or reply_to is None:
        return
    repo = context.bot_data["parcel_repo"]
    active = await repo.list_active_for_user(user_id=user.id)
    archived = await repo.list_archived_for_user(user_id=user.id)
    delivered = [p for p in active if p.status.value == "Delivered"] + list(archived)
    if not delivered:
        await reply_to.reply_text(messages.no_delivered_parcels(), parse_mode="HTML")
        return
    text = "\n".join(
        f"✅ <code>{messages.esc(p.tracking_number)}</code> {messages.esc(p.name or '')}".rstrip()
        for p in delivered
    )
    await reply_to.reply_text(text, parse_mode="HTML")


async def cmd_stats(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show rich bot stats (owner only)."""
    from collections import Counter  # noqa: PLC0415

    from parcel_tracker.bot.formatting import fmt_event_time, status_label  # noqa: PLC0415

    user = update.effective_user
    reply_to = update.effective_message
    if user is None or reply_to is None:
        return
    if not _is_owner(context, user.id):
        await reply_to.reply_text(messages.owner_only(), parse_mode="HTML")
        return

    bd = context.bot_data
    config = bd["config"]
    active = await bd["parcel_repo"].list_active_for_user(user_id=user.id)
    archived = await bd["parcel_repo"].list_archived_for_user(user_id=user.id)

    status_counts: Counter[Any] = Counter(p.status for p in active)
    by_status_parts = [f"{len(active)} active"]
    for st in status_counts:
        by_status_parts.append(f"{status_counts[st]} {status_label(st).lower()}")
    by_status_parts.append(f"{len(archived)} archived")
    by_status = " · ".join(by_status_parts)

    carrier_counts: Counter[str] = Counter((p.carrier_name or "?") for p in active)
    by_carrier = " · ".join(f"{c} {n}" for c, n in carrier_counts.most_common(6))

    events = await bd["parcel_repo"].count_events_for_user(user_id=user.id)
    last_check = ""
    checks = [p.last_check_at for p in active if p.last_check_at is not None]
    if checks:
        last_check = fmt_event_time(max(checks).isoformat())

    quarantined = await bd["health_repo"].count_quarantined()
    registry = bd.get("registry")
    if registry is None:
        total_trackers = 0
    elif hasattr(registry, "iter_all"):
        total_trackers = sum(1 for _ in registry.iter_all())
    else:
        total_trackers = len(registry)

    user_ids: set[int] = set(await bd["user_repo"].get_allowed_user_ids())
    owner_id = getattr(config, "owner_id", None)
    if owner_id is not None:
        user_ids.add(owner_id)
    user_ids.update(getattr(config, "allowed_user_ids", ()) or ())

    text = messages.stats_full(
        by_status=by_status,
        by_carrier=by_carrier,
        events=events,
        last_check=last_check,
        quarantined=quarantined,
        total_trackers=total_trackers,
        users=len(user_ids),
    )
    await reply_to.reply_text(text, parse_mode="HTML")
