"""Jinja2 rendering with the bot's gettext catalogs and presentation helpers."""

from __future__ import annotations

import functools
import hashlib
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import jinja2
from aiohttp import web
from markupsafe import Markup

from parcel_tracker.bot.formatting import fmt_event_time, status_label
from parcel_tracker.core.shipments import (
    PROGRESS_STEPS,
    StatusGroup,
    is_stalled,
    progress_index,
    status_group,
)
from parcel_tracker.core.stats import WeekBucket
from parcel_tracker.db.models import Parcel, ShipmentStatus
from parcel_tracker.i18n import LOCALE_DIR, _, _n, available_locales, translator_for, using
from parcel_tracker.web.charts import Series, grouped_columns
from parcel_tracker.web.keys import JINJA

TEMPLATES = Path(__file__).parent / "templates"
STATIC = Path(__file__).parent / "static"

LANGUAGE_NAMES = {"en": "English", "it": "Italiano"}

_GROUP_CLASS = {
    StatusGroup.PENDING: "pending",
    StatusGroup.TRANSIT: "transit",
    StatusGroup.OUT_FOR_DELIVERY: "out",
    StatusGroup.ATTENTION: "attention",
    StatusGroup.DELIVERED: "delivered",
}
# 12px stroke icons (currentColor) so every pill pairs its colour with a shape.
_ICON_PATHS = {
    "pending": '<circle cx="8" cy="8" r="4.5" fill="none" stroke="currentColor" stroke-width="1.8"/>',
    "transit": '<path d="M2.5 8h9M8.5 4.5 12 8l-3.5 3.5" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/>',
    "out": '<path d="M1.5 4.5h7.5v6H1.5zM9 6.5h3l2 2.2v1.8H9" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linejoin="round"/><circle cx="4.5" cy="11.5" r="1.4" fill="currentColor"/><circle cx="11.5" cy="11.5" r="1.4" fill="currentColor"/>',
    "delivered": '<path d="M3 8.5 6.5 12 13 4.5" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>',
    "attention": '<path d="M8 3v6" stroke="currentColor" stroke-width="2" stroke-linecap="round"/><circle cx="8" cy="12.5" r="1.3" fill="currentColor"/>',
    "returned": '<path d="M5.5 3.5 2.5 6.5l3 3M3 6.5h6.5a4 4 0 0 1 0 8H7" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/>',
    "stalled": '<path d="M5.5 4v8M10.5 4v8" stroke="currentColor" stroke-width="2" stroke-linecap="round"/>',
}
_STATUS_ICON = {
    ShipmentStatus.NOT_FOUND: "pending",
    ShipmentStatus.INFO_RECEIVED: "pending",
    ShipmentStatus.PICKUP: "transit",
    ShipmentStatus.IN_TRANSIT: "transit",
    ShipmentStatus.CUSTOMS: "transit",
    ShipmentStatus.OUT_FOR_DELIVERY: "out",
    ShipmentStatus.DELIVERED: "delivered",
    ShipmentStatus.UNDELIVERED: "attention",
    ShipmentStatus.EXCEPTION: "attention",
    ShipmentStatus.ALERT: "attention",
    ShipmentStatus.RETURNED: "returned",
    ShipmentStatus.EXPIRED: "attention",
}


def icon(name: str) -> Markup:
    """Inline SVG icon (decorative: the label next to it carries the meaning)."""
    return Markup(  # noqa: S704  # nosec B704 — constant markup from _ICON_PATHS
        '<svg class="ico" width="12" height="12" viewBox="0 0 16 16" aria-hidden="true" '
        f'focusable="false">{_ICON_PATHS.get(name, _ICON_PATHS["pending"])}</svg>'
    )


def status_icon(status: ShipmentStatus) -> Markup:
    return icon(_STATUS_ICON.get(status, "pending"))


def _gettext(message: str, **variables: Any) -> str:
    text = _(message)
    return text % variables if variables else text


def _ngettext(singular: str, plural: str, n: int, **variables: Any) -> str:
    variables.setdefault("num", n)
    return _n(singular, plural, n) % variables


def build_environment() -> jinja2.Environment:
    env = jinja2.Environment(
        loader=jinja2.FileSystemLoader(str(TEMPLATES)),
        autoescape=jinja2.select_autoescape(("html", "xml"), default=True),
        extensions=["jinja2.ext.i18n"],
        trim_blocks=True,
        lstrip_blocks=True,
        undefined=jinja2.StrictUndefined,
    )
    # newstyle gettext: {{ _("Hello %(name)s", name=x) }} escapes variables.
    env.install_gettext_callables(_gettext, _ngettext, newstyle=True)  # type: ignore[attr-defined]
    env.globals.update(
        status_label=status_label,
        status_class=lambda s: _GROUP_CLASS[status_group(s)],
        status_icon=status_icon,
        icon=icon,
        progress_steps=PROGRESS_STEPS,
        progress_index=progress_index,
        fmt_event_time=fmt_event_time,
        language_names=LANGUAGE_NAMES,
        groups=StatusGroup,
        static=static_url,
        weekly_chart=weekly_chart,
    )
    env.filters["iso"] = iso
    env.filters["days"] = days_since
    return env


@functools.cache
def static_url(name: str) -> str:
    """URL of a static asset with a content hash, so browsers refetch after upgrades."""
    digest = hashlib.sha256((STATIC / name).read_bytes()).hexdigest()[:10]
    return f"/static/{name}?v={digest}"


def weekly_chart(weeks: list[WeekBucket]) -> Markup:
    """Shipped vs delivered per week (called while the page's language is active)."""
    titles = [
        _("Week of {date}: {shipped} shipped, {delivered} delivered").format(
            date=w.week_start.isoformat(), shipped=w.shipped, delivered=w.delivered
        )
        for w in weeks
    ]
    return grouped_columns(
        [w.week_start.isoformat() for w in weeks],
        titles,
        [
            Series(_("Shipped"), "s1", [w.shipped for w in weeks]),
            Series(_("Delivered"), "s2", [w.delivered for w in weeks]),
        ],
        aria_label=_("Shipments shipped and delivered per week"),
    )


def iso(value: datetime | None) -> str:
    if value is None:
        return ""
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def days_since(value: datetime | None, now: datetime | None = None) -> int | None:
    if value is None:
        return None
    now = now or datetime.now(UTC)
    return max(0, (now - value).days)


def parcel_flags(parcel: Parcel, now: datetime, stall_days: int) -> dict[str, Any]:
    """Derived presentation facts for one parcel."""
    return {
        "stalled": is_stalled(parcel, now, stall_days),
        "group": status_group(parcel.status).value,
    }


def pick_language(request: web.Request, default: str) -> str:
    """Best supported language from Accept-Language (public pages)."""
    supported = available_locales(LOCALE_DIR)
    header = request.headers.get("Accept-Language", "")
    for part in header.split(","):
        code = part.split(";")[0].strip().lower()[:2]
        if code in supported:
            return code
    return default if default in supported else "en"


def render(
    request: web.Request,
    template: str,
    context: dict[str, Any],
    *,
    language: str,
    status: int = 200,
) -> web.Response:
    env: jinja2.Environment = request.app[JINJA]
    locale = language if language in available_locales(LOCALE_DIR) else "en"
    with using(translator_for(locale, LOCALE_DIR)):
        body = env.get_template(template).render(lang=locale, request_path=request.path, **context)
    return web.Response(text=body, content_type="text/html", status=status, charset="utf-8")
