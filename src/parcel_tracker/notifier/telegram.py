"""Telegram notifier — formatted messages for status updates."""

from __future__ import annotations

import logging
from typing import Any, Protocol

from parcel_tracker.bot import messages
from parcel_tracker.db.models import ShipmentStatus, TrackingEvent
from parcel_tracker.observability.metrics import (
    TELEGRAM_ERRORS_TOTAL,
    TELEGRAM_SENT_TOTAL,
)

logger = logging.getLogger(__name__)


class _BotLike(Protocol):
    # reply_markup/photo are typed Any (not object) so the real PTB ExtBot — whose
    # params are narrower unions — structurally satisfies this Protocol (params are
    # contravariant: an `object` param would demand ExtBot accept ANY value, which it does not).
    async def send_message(
        self, *, chat_id: int, text: str, parse_mode: str = "HTML", reply_markup: Any = None
    ) -> object: ...

    async def send_photo(
        self, *, chat_id: int, photo: Any, caption: str, parse_mode: str = "HTML"
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
        title = messages.esc(parcel_name or tracking_number)
        lines = [
            f"{emoji} <b>{title}</b>",
            f"<code>{messages.esc(tracking_number)}</code>",
            "",
            f"Status: <i>{old_status.value}</i> → <b>{new_status.value}</b>",
        ]
        if last_event:
            lines.append("")
            lines.append(f"📍 {messages.esc(last_event.description)}")
            if last_event.location:
                lines.append(f"   {messages.esc(last_event.location)}")
            if last_event.time:
                lines.append(f"   <i>{messages.esc(last_event.time)}</i>")

        text = "\n".join(lines)

        try:
            await self._bot.send_message(chat_id=chat_id, text=text, parse_mode="HTML")
        except Exception as exc:  # noqa: BLE001 (instrumentation)
            TELEGRAM_ERRORS_TOTAL.labels(error_class=type(exc).__name__).inc()
            raise
        else:
            TELEGRAM_SENT_TOTAL.labels(status_value=new_status.value).inc()

    async def send_delivery_confirmation(
        self,
        *,
        chat_id: int,
        tracking_number: str,
        parcel_name: str | None,
        location: str | None,
    ) -> None:
        from parcel_tracker.bot.keyboards import delivery_confirm_keyboard  # noqa: PLC0415

        title = parcel_name or tracking_number
        text = messages.delivery_confirm_prompt(title, tracking_number)
        if location:
            text += f"\n📍 {messages.esc(location)}"
        try:
            await self._bot.send_message(
                chat_id=chat_id,
                text=text,
                parse_mode="HTML",
                reply_markup=delivery_confirm_keyboard(tracking_number),
            )
        except Exception as exc:  # noqa: BLE001
            TELEGRAM_ERRORS_TOTAL.labels(error_class=type(exc).__name__).inc()
            raise
        else:
            TELEGRAM_SENT_TOTAL.labels(status_value=ShipmentStatus.DELIVERED.value).inc()

    async def send_events_update(  # noqa: PLR0913
        self,
        *,
        chat_id: int,
        tracking_number: str,
        parcel_name: str | None,
        old_status: ShipmentStatus,
        new_status: ShipmentStatus,
        status_changed: bool,
        new_events: list[TrackingEvent],
        location: str | None,
        map_png: bytes | None = None,
    ) -> None:
        emoji = _STATUS_EMOJI.get(new_status, "📦")
        title = messages.esc(parcel_name or tracking_number)
        lines = [f"{emoji} <b>{title}</b>", f"<code>{messages.esc(tracking_number)}</code>", ""]
        if status_changed:
            lines.append(f"Status: <i>{old_status.value}</i> → <b>{new_status.value}</b>")
        if location:
            lines.append(f"📍 {messages.esc(location)}")
        if new_events:
            lines.append("")
            lines.append("🆕 <b>Updates:</b>")
            for ev in new_events:
                row = f"• <i>{messages.esc(ev.time)}</i> — {messages.esc(ev.description)}"
                if ev.location:
                    row += f" ({messages.esc(ev.location)})"
                lines.append(row)
        text = "\n".join(lines)
        if map_png is not None:
            await self._send_photo_instrumented(
                chat_id=chat_id, photo=map_png, caption=text, status_value=new_status.value
            )
            return
        await self._send_message_instrumented(
            chat_id=chat_id, text=text, status_value=new_status.value
        )

    async def _send_message_instrumented(
        self, *, chat_id: int, text: str, status_value: str
    ) -> None:
        """send_message with success/failure metric instrumentation."""
        try:
            await self._bot.send_message(chat_id=chat_id, text=text, parse_mode="HTML")
        except Exception as exc:  # noqa: BLE001
            TELEGRAM_ERRORS_TOTAL.labels(error_class=type(exc).__name__).inc()
            raise
        else:
            TELEGRAM_SENT_TOTAL.labels(status_value=status_value).inc()

    async def _send_photo_instrumented(
        self, *, chat_id: int, photo: bytes, caption: str, status_value: str
    ) -> None:
        """send_photo with success/failure metric instrumentation."""
        try:
            await self._bot.send_photo(
                chat_id=chat_id, photo=photo, caption=caption, parse_mode="HTML"
            )
        except Exception as exc:  # noqa: BLE001
            TELEGRAM_ERRORS_TOTAL.labels(error_class=type(exc).__name__).inc()
            raise
        else:
            TELEGRAM_SENT_TOTAL.labels(status_value=status_value).inc()
