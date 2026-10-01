"""Telegram notifier — formatted messages for status updates."""

from __future__ import annotations

import html
import logging
import re
from collections.abc import Awaitable, Callable
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


# Telegram limits, counted in UTF-16 code units of the text after HTML parsing.
MAX_MESSAGE_CHARS = 4096
MAX_CAPTION_CHARS = 1024
# Per-field caps (raw characters) so one oversized carrier string cannot by itself
# exceed a message: name/carrier/location/description are untrusted and unbounded.
_MAX_NAME_CHARS = 100
_MAX_LOCATION_CHARS = 200
_MAX_DESCRIPTION_CHARS = 400

_TAG_RE = re.compile(r"<[^>]+>")

EventsSentCallback = Callable[[list[TrackingEvent]], Awaitable[None]]


def _clip(value: str, limit: int) -> str:
    return value if len(value) <= limit else value[: limit - 1] + "…"


def _visible_len(html_text: str) -> int:
    """Length as Telegram counts it: tags stripped, entities decoded, UTF-16 units."""
    plain = html.unescape(_TAG_RE.sub("", html_text))
    return len(plain.encode("utf-16-le")) // 2


def _pack_rows(
    head: list[str],
    rows: list[tuple[str, TrackingEvent]],
    tail: list[str],
    limit: int,
) -> list[tuple[str, list[TrackingEvent]]]:
    """Greedily pack event rows into messages of at most ``limit`` visible chars.

    Every message repeats ``head`` and the last one carries ``tail``. Field caps keep
    a single row well under the limit, so each chunk holds at least one row.
    """
    chunks: list[tuple[list[str], list[TrackingEvent]]] = [([], [])]
    for row, ev in rows:
        lines, events = chunks[-1]
        candidate = "\n".join([*head, *lines, row, *tail])
        if lines and _visible_len(candidate) > limit:
            chunks.append(([row], [ev]))
        else:
            lines.append(row)
            events.append(ev)
    return [("\n".join([*head, *lines, *tail]), events) for lines, events in chunks]


def _render_event_parts(  # noqa: PLR0913
    *,
    tracking_number: str,
    parcel_name: str | None,
    carrier_name: str | None,
    old_status: ShipmentStatus,
    new_status: ShipmentStatus,
    status_changed: bool,
    new_events: list[TrackingEvent],
    location: str | None,
) -> tuple[list[str], list[str], list[tuple[str, TrackingEvent]], list[str]]:
    """Lines of an events update: (title, head, event rows, tail)."""
    from parcel_tracker.bot.formatting import (  # noqa: PLC0415
        fmt_event_time,
        status_emoji,
        status_label,
    )

    emoji = status_emoji(new_status)
    if parcel_name:
        header = messages.esc(_clip(parcel_name, _MAX_NAME_CHARS))
    elif carrier_name:
        header = (
            f"{messages.esc(_clip(carrier_name, _MAX_NAME_CHARS))} — {status_label(new_status)}"
        )
    else:
        header = status_label(new_status)

    title = [f"{emoji} <b>{header}</b>", f"<code>{messages.esc(tracking_number)}</code>"]
    head = list(title)
    if status_changed and parcel_name:
        head.append(f"{status_label(old_status)} → <b>{status_label(new_status)}</b>")
    if location:
        head.append("")
        head.append(f"📍 {messages.esc(_clip(location, _MAX_LOCATION_CHARS))}")
    rows: list[tuple[str, TrackingEvent]] = []
    for ev in new_events:
        when = fmt_event_time(ev.time)
        description = _clip(ev.description, _MAX_DESCRIPTION_CHARS)
        row = f"• {messages.esc(when)} — {messages.esc(description)}"
        if ev.location:
            row += f" ({messages.esc(_clip(ev.location, _MAX_LOCATION_CHARS))})"
        rows.append((row, ev))
    if rows:
        head.append("")
        head.append(f"🆕 <b>{messages.esc(_updates_label())}</b>")
    tail: list[str] = []
    if not parcel_name:
        tail.append("")
        tail.append(f"<i>{messages.name_hint()}</i>")
    return title, head, rows, tail


def _updates_label() -> str:
    from parcel_tracker.i18n import _  # noqa: PLC0415

    return _("Updates:")


class TelegramNotifier:
    def __init__(self, *, bot: _BotLike) -> None:
        self._bot = bot

    async def send_status_update(  # noqa: PLR0913
        self,
        *,
        chat_id: int,
        tracking_number: str,
        parcel_name: str | None,
        carrier_name: str | None = None,
        old_status: ShipmentStatus,
        new_status: ShipmentStatus,
        last_event: TrackingEvent | None,
    ) -> None:
        from parcel_tracker.bot.formatting import (  # noqa: PLC0415
            fmt_event_time,
            status_emoji,
            status_label,
        )

        emoji = status_emoji(new_status)
        if parcel_name:
            header = messages.esc(parcel_name)
        elif carrier_name:
            header = f"{messages.esc(carrier_name)} — {status_label(new_status)}"
        else:
            header = status_label(new_status)

        lines = [
            f"{emoji} <b>{header}</b>",
            f"<code>{messages.esc(tracking_number)}</code>",
            "",
            f"{status_label(old_status)} → <b>{status_label(new_status)}</b>",
        ]
        if last_event:
            lines.append("")
            lines.append(f"📍 {messages.esc(last_event.description)}")
            if last_event.location:
                lines.append(f"   {messages.esc(last_event.location)}")
            if last_event.time:
                lines.append(f"   <i>{messages.esc(fmt_event_time(last_event.time))}</i>")

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

        text = messages.delivery_confirm_prompt(parcel_name, tracking_number)
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
        carrier_name: str | None = None,
        old_status: ShipmentStatus,
        new_status: ShipmentStatus,
        status_changed: bool,
        new_events: list[TrackingEvent],
        location: str | None,
        map_png: bytes | None = None,
        on_events_sent: EventsSentCallback | None = None,
    ) -> None:
        """Send the update, split across messages when it exceeds Telegram's limits.

        ``on_events_sent`` is awaited after each successful send with the events that
        message carried, so a caller can mark them notified per batch: a failure part
        way through then only re-sends the events that were not delivered yet.
        """
        title, head, rows, tail = _render_event_parts(
            tracking_number=tracking_number,
            parcel_name=parcel_name,
            carrier_name=carrier_name,
            old_status=old_status,
            new_status=new_status,
            status_changed=status_changed,
            new_events=new_events,
            location=location,
        )
        text = "\n".join([*head, *(r for r, _ev in rows), *tail])
        status_value = new_status.value
        if map_png is not None:
            if _visible_len(text) <= MAX_CAPTION_CHARS:
                await self._send_photo_instrumented(
                    chat_id=chat_id, photo=map_png, caption=text, status_value=status_value
                )
                if on_events_sent is not None:
                    await on_events_sent(list(new_events))
                return
            # Too long for a caption: the map goes with a short caption, the events
            # follow as regular messages.
            await self._send_photo_instrumented(
                chat_id=chat_id,
                photo=map_png,
                caption="\n".join(title),
                status_value=status_value,
            )
        for chunk_text, chunk_events in _pack_rows(head, rows, tail, MAX_MESSAGE_CHARS):
            await self._send_message_instrumented(
                chat_id=chat_id, text=chunk_text, status_value=status_value
            )
            if on_events_sent is not None:
                await on_events_sent(chunk_events)

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
