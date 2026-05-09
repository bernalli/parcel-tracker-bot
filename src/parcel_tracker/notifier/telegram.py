"""Telegram notifier — formatted messages for status updates."""

from __future__ import annotations

import logging
from typing import Protocol

from parcel_tracker.db.models import ShipmentStatus, TrackingEvent
from parcel_tracker.observability.metrics import (
    TELEGRAM_ERRORS_TOTAL,
    TELEGRAM_SENT_TOTAL,
)

logger = logging.getLogger(__name__)


class _BotLike(Protocol):
    async def send_message(
        self, *, chat_id: int, text: str, parse_mode: str = "HTML"
    ) -> object: ...


_STATUS_EMOJI: dict[ShipmentStatus, str] = {
    ShipmentStatus.NOT_FOUND: "❓",
    ShipmentStatus.INFO_RECEIVED: "ℹ️",
    ShipmentStatus.PICKUP: "📦",
    ShipmentStatus.IN_TRANSIT: "🚚",
    ShipmentStatus.OUT_FOR_DELIVERY: "🚛",
    ShipmentStatus.CUSTOMS: "🛃",
    ShipmentStatus.DELIVERED: "✅",
    ShipmentStatus.UNDELIVERED: "❌",
    ShipmentStatus.EXCEPTION: "⚠️",
    ShipmentStatus.RETURNED: "↩️",
    ShipmentStatus.EXPIRED: "⏰",
    ShipmentStatus.ALERT: "🚨",
}


class TelegramNotifier:
    def __init__(self, *, bot: _BotLike) -> None:
        self._bot = bot

    async def send_status_update(
        self,
        *,
        chat_id: int,
        tracking_number: str,
        parcel_name: str | None,
        old_status: ShipmentStatus,
        new_status: ShipmentStatus,
        last_event: TrackingEvent | None,
    ) -> None:
        emoji = _STATUS_EMOJI.get(new_status, "📦")
        title = parcel_name or tracking_number
        lines = [
            f"{emoji} <b>{title}</b>",
            f"<code>{tracking_number}</code>",
            "",
            f"Status: <i>{old_status.value}</i> → <b>{new_status.value}</b>",
        ]
        if last_event:
            lines.append("")
            lines.append(f"📍 {last_event.description}")
            if last_event.location:
                lines.append(f"   {last_event.location}")
            if last_event.time:
                lines.append(f"   <i>{last_event.time}</i>")

        text = "\n".join(lines)

        try:
            await self._bot.send_message(chat_id=chat_id, text=text, parse_mode="HTML")
        except Exception as exc:  # noqa: BLE001 (instrumentation)
            TELEGRAM_ERRORS_TOTAL.labels(error_class=type(exc).__name__).inc()
            raise
        else:
            TELEGRAM_SENT_TOTAL.labels(status_value=new_status.value).inc()
