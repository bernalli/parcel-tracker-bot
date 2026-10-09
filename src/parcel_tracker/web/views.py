"""Dashboard pages (server-rendered HTML)."""

from __future__ import annotations

import asyncio
import logging
from collections import OrderedDict
from collections.abc import Iterable
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urlencode

from aiohttp import web

from parcel_tracker.bot import throttle
from parcel_tracker.core.csv_io import CsvImportError, export_csv, import_csv
from parcel_tracker.core.shipments import (
    DETAIL_FIELDS_WEB,
    AddOutcome,
    ShipmentInput,
    add_shipment,
    clean_tags,
    clip_field,
    extract_code_and_name,
    is_stalled,
    needs_attention,
    share_token_for,
    strip_list_marker,
)
from parcel_tracker.core.stats import carrier_label, compute_stats, delivery_days
from parcel_tracker.db.models import Parcel, ShipmentStatus
from parcel_tracker.db.repository import ParcelRepository
from parcel_tracker.db.settings_repository import SHOP_NAME, SettingsRepository
from parcel_tracker.i18n import LOCALE_DIR, available_locales
from parcel_tracker.web.auth import bot_data, session, user_id, web_repo
from parcel_tracker.web.keys import MAP_CACHE, SESSION
from parcel_tracker.web.render import pick_language, render

logger = logging.getLogger(__name__)

PAGE_SIZE = 50
VIEWS = ("active", "attention", "delivered", "archived", "all")
_MAP_CACHE_SIZE = 64
_TOKEN_NAME_MAX = 40
_SHOP_NAME_MAX = 60


def _repo(request: web.Request) -> ParcelRepository:
    repo: ParcelRepository = bot_data(request)["parcel_repo"]
    return repo


def _settings(request: web.Request) -> SettingsRepository:
    repo: SettingsRepository = bot_data(request)["settings"]
    return repo


def _stall_days(request: web.Request) -> int:
    return int(getattr(bot_data(request)["config"], "stall_alert_days", 0) or 0)


def _now() -> datetime:
    return datetime.now(UTC)


def _redirect(location: str, **query: str | int) -> web.HTTPSeeOther:
    if query:
        location += ("&" if "?" in location else "?") + urlencode(query)
    return web.HTTPSeeOther(location)


async def page(
    request: web.Request,
    template: str,
    context: dict[str, Any],
    *,
    public: bool = False,
    status: int = 200,
) -> web.Response:
    """Render a page with the shared layout context."""
    bd = bot_data(request)
    config = bd["config"]
    current = request.get(SESSION)
    if current is not None and not public:
        language = await bd["user_repo"].get_language(
            current.user_id, default=config.default_language
        )
        shop = await _settings(request).shop_name(current.user_id)
    else:
        language = pick_language(request, config.default_language)
        shop = None
    base: dict[str, Any] = {
        "csrf": current.csrf_token if current is not None else "",
        "signed_in": current is not None and not public,
        "shop_name": shop,
        "maps_enabled": bd.get("map_renderer") is not None and bd.get("geocoder") is not None,
        "flash": request.query.get("msg", ""),
        "flash_n": _int(request.query.get("n"), 0),
        "flash_m": _int(request.query.get("m"), 0),
        "stall_days": _stall_days(request),
        "now": _now(),
    }
    base.update(context)
    return render(request, template, base, language=language, status=status)


def _int(raw: str | None, default: int) -> int:
    try:
        return int(raw) if raw is not None else default
    except ValueError:
        return default


async def _parcel_or_404(request: web.Request) -> Parcel:
    parcel_id = _int(request.match_info.get("parcel_id"), -1)
    parcel = await _repo(request).get_by_id_for_user(parcel_id, user_id=user_id(request))
    if parcel is None:
        raise web.HTTPNotFound(text="Shipment not found")
    return parcel


# --- dashboard ----------------------------------------------------------------


async def dashboard(request: web.Request) -> web.StreamResponse:
    uid = user_id(request)
    parcels = await _repo(request).list_all_for_user(user_id=uid)
    now = _now()
    stall_days = _stall_days(request)
    stats = compute_stats(parcels, now=now, stall_days=stall_days)
    attention = sorted(
        (p for p in parcels if needs_attention(p, now, stall_days)),
        key=lambda p: p.last_change_at or p.created_at or now,
    )
    delivered = sorted(
        (p for p in parcels if p.delivered_at is not None),
        key=lambda p: p.delivered_at or now,
        reverse=True,
    )
    return await page(
        request,
        "dashboard.html",
        {
            "stats": stats,
            "attention": attention[:8],
            "attention_total": len(attention),
            "recent_delivered": delivered[:6],
            "delivery_days": delivery_days,
            "has_parcels": bool(parcels),
            "is_stalled_fn": lambda p: is_stalled(p, now, stall_days),
        },
    )


# --- shipments list ------------------------------------------------------------


def _matches(parcel: Parcel, query: str) -> bool:
    haystack = " ".join(
        v
        for v in (
            parcel.tracking_number,
            parcel.name,
            parcel.order_ref,
            parcel.recipient,
            parcel.destination,
            parcel.notes,
            parcel.carrier_name,
            " ".join(parcel.tags),
        )
        if v
    ).casefold()
    return all(term in haystack for term in query.casefold().split())


def filter_parcels(  # noqa: PLR0913
    parcels: Iterable[Parcel],
    *,
    view: str,
    query: str,
    carrier: str,
    tag: str,
    now: datetime,
    stall_days: int,
) -> list[Parcel]:
    """Apply the list filters; newest activity first."""
    selected: list[Parcel] = []
    for p in parcels:
        if view == "active" and not p.is_active:
            continue
        if view == "attention" and not needs_attention(p, now, stall_days):
            continue
        if view == "delivered" and p.status is not ShipmentStatus.DELIVERED:
            continue
        if view == "archived" and p.is_active:
            continue
        if carrier and carrier_label(p) != carrier:
            continue
        if tag and tag not in p.tags:
            continue
        if query and not _matches(p, query):
            continue
        selected.append(p)
    selected.sort(key=lambda p: p.last_change_at or p.created_at or now, reverse=True)
    return selected


def _list_params(request: web.Request) -> dict[str, str]:
    view = request.query.get("view", "active")
    return {
        "view": view if view in VIEWS else "active",
        "q": request.query.get("q", "").strip()[:100],
        "carrier": request.query.get("carrier", "").strip(),
        "tag": request.query.get("tag", "").strip().lower(),
    }


async def shipments(request: web.Request) -> web.StreamResponse:
    uid = user_id(request)
    every = await _repo(request).list_all_for_user(user_id=uid)
    params = _list_params(request)
    now = _now()
    stall_days = _stall_days(request)
    selected = filter_parcels(
        every,
        view=params["view"],
        query=params["q"],
        carrier=params["carrier"],
        tag=params["tag"],
        now=now,
        stall_days=stall_days,
    )
    page_no = max(1, _int(request.query.get("page"), 1))
    pages = max(1, -(-len(selected) // PAGE_SIZE))
    page_no = min(page_no, pages)
    counts = {
        v: len(
            filter_parcels(
                every, view=v, query="", carrier="", tag="", now=now, stall_days=stall_days
            )
        )
        for v in VIEWS
    }
    query_base = {k: v for k, v in params.items() if v}
    return await page(
        request,
        "shipments.html",
        {
            "params": params,
            "rows": selected[(page_no - 1) * PAGE_SIZE : page_no * PAGE_SIZE],
            "total": len(selected),
            "page_no": page_no,
            "pages": pages,
            "counts": counts,
            "views": VIEWS,
            "carriers": sorted({carrier_label(p) for p in every}),
            "tags": sorted({t for p in every for t in p.tags}),
            "query_base": urlencode(query_base),
            "page_url": lambda n: "/shipments?" + urlencode({**query_base, "page": n}),
            "is_stalled": lambda p: is_stalled(p, now, stall_days),
        },
    )


async def export(request: web.Request) -> web.StreamResponse:
    uid = user_id(request)
    every = await _repo(request).list_all_for_user(user_id=uid)
    params = _list_params(request)
    if "view" not in request.query:
        params["view"] = "all"
    selected = filter_parcels(
        every,
        view=params["view"],
        query=params["q"],
        carrier=params["carrier"],
        tag=params["tag"],
        now=_now(),
        stall_days=_stall_days(request),
    )
    stamp = _now().strftime("%Y%m%d")
    return web.Response(
        body=export_csv(selected).encode("utf-8-sig"),
        content_type="text/csv",
        charset="utf-8",
        headers={"Content-Disposition": f'attachment; filename="shipments-{stamp}.csv"'},
    )


# --- add -------------------------------------------------------------------------


async def new_shipment(request: web.Request) -> web.StreamResponse:
    return await page(request, "new.html", {"form": {}, "error": None})


def _max_active(request: web.Request) -> int:
    return int(getattr(bot_data(request)["config"], "max_active_shipments", 0) or 0)


async def create_shipment(request: web.Request) -> web.StreamResponse:
    form = await request.post()
    uid = user_id(request)
    bulk = str(form.get("codes") or "").strip()
    if bulk:
        return await _create_bulk(request, uid, bulk)
    data = ShipmentInput(
        tracking_number=str(form.get("tracking_number") or ""),
        name=str(form.get("name") or "") or None,
        order_ref=str(form.get("order_ref") or "") or None,
        recipient=str(form.get("recipient") or "") or None,
        destination=str(form.get("destination") or "") or None,
        notes=str(form.get("notes") or "") or None,
        tags=clean_tags(str(form.get("tags") or "")),
    )
    outcome, parcel = await add_shipment(
        _repo(request), user_id=uid, data=data, max_active=_max_active(request)
    )
    if outcome is AddOutcome.ADDED and parcel is not None and parcel.id is not None:
        raise _redirect(f"/shipments/{parcel.id}", msg="added")
    return await page(
        request,
        "new.html",
        {"form": dict(form), "error": outcome.value, "limit": _max_active(request)},
        status=400,
    )


async def _create_bulk(request: web.Request, uid: int, text: str) -> web.StreamResponse:
    detector = bot_data(request).get("detector")
    counts = dict.fromkeys(AddOutcome, 0)
    for raw in text.splitlines()[:500]:
        line = strip_list_marker(raw)
        if not line:
            continue
        code, name = extract_code_and_name(line, detector)
        outcome, _parcel = await add_shipment(
            _repo(request),
            user_id=uid,
            data=ShipmentInput(tracking_number=code, name=name),
            max_active=_max_active(request),
        )
        counts[outcome] += 1
    raise _redirect(
        "/shipments",
        msg="bulk",
        n=counts[AddOutcome.ADDED],
        m=counts[AddOutcome.DUPLICATE] + counts[AddOutcome.INVALID] + counts[AddOutcome.LIMIT],
    )


# --- detail & actions ------------------------------------------------------------


def share_url(request: web.Request, token: str | None) -> str | None:
    if not token:
        return None
    return f"{bot_data(request)['config'].web_public_url}/t/{token}"


async def shipment_detail(request: web.Request) -> web.StreamResponse:
    parcel = await _parcel_or_404(request)
    events = await _repo(request).get_history(
        parcel.tracking_number, limit=200, user_id=parcel.user_id
    )
    now = _now()
    return await page(
        request,
        "shipment.html",
        {
            "p": parcel,
            "events": events,
            "share_url": share_url(request, parcel.share_token),
            "stalled": is_stalled(parcel, now, _stall_days(request)),
            "transit_days": delivery_days(parcel),
        },
    )


async def update_shipment(request: web.Request) -> web.StreamResponse:
    parcel = await _parcel_or_404(request)
    form = await request.post()
    fields: dict[str, str | list[str] | None] = {
        key: clip_field(key, str(form.get(key) or "")) for key in DETAIL_FIELDS_WEB
    }
    fields["tags"] = clean_tags(str(form.get("tags") or ""))
    await _repo(request).update_details(parcel.tracking_number, user_id=parcel.user_id, **fields)
    raise _redirect(f"/shipments/{parcel.id}", msg="saved")


async def refresh_shipment(request: web.Request) -> web.StreamResponse:
    from parcel_tracker.core.scheduler import check_parcel_now  # noqa: PLC0415

    parcel = await _parcel_or_404(request)
    wait = throttle.REFRESH.wait_seconds(parcel.user_id)
    if wait:
        raise _redirect(f"/shipments/{parcel.id}", msg="wait", n=wait)
    try:
        outcome = await check_parcel_now(
            bot_data(request), user_id=parcel.user_id, tracking_number=parcel.tracking_number
        )
    except Exception:  # noqa: BLE001 — show a friendly message, keep the page usable
        logger.warning("web refresh failed for %s", parcel.tracking_number, exc_info=True)
        outcome = "failed"
    msg = "refresh_failed" if outcome in ("failed", "quarantined", "no_tracker") else "refreshed"
    raise _redirect(f"/shipments/{parcel.id}", msg=msg)


async def archive_shipment(request: web.Request) -> web.StreamResponse:
    parcel = await _parcel_or_404(request)
    await _repo(request).deactivate(parcel.tracking_number, user_id=parcel.user_id)
    raise _redirect(f"/shipments/{parcel.id}", msg="archived")


async def restore_shipment(request: web.Request) -> web.StreamResponse:
    parcel = await _parcel_or_404(request)
    max_active = _max_active(request)
    if (
        max_active
        and await _repo(request).count_active_for_user(user_id=parcel.user_id) >= max_active
    ):
        raise _redirect(f"/shipments/{parcel.id}", msg="limit", n=max_active)
    # Re-creating reactivates the row and resets a terminal status so polling resumes.
    await _repo(request).create(
        Parcel(tracking_number=parcel.tracking_number, user_id=parcel.user_id)
    )
    raise _redirect(f"/shipments/{parcel.id}", msg="restored")


async def delete_shipment(request: web.Request) -> web.StreamResponse:
    parcel = await _parcel_or_404(request)
    await _repo(request).delete_for_user(parcel.tracking_number, user_id=parcel.user_id)
    raise _redirect("/shipments", msg="deleted")


async def share_shipment(request: web.Request) -> web.StreamResponse:
    parcel = await _parcel_or_404(request)
    token = share_token_for(parcel)
    await _repo(request).set_share_token(
        parcel.tracking_number, user_id=parcel.user_id, token=token
    )
    raise _redirect(f"/shipments/{parcel.id}", msg="shared")


async def unshare_shipment(request: web.Request) -> web.StreamResponse:
    parcel = await _parcel_or_404(request)
    await _repo(request).set_share_token(parcel.tracking_number, user_id=parcel.user_id, token=None)
    raise _redirect(f"/shipments/{parcel.id}", msg="unshared")


async def shipment_map(request: web.Request) -> web.StreamResponse:
    parcel = await _parcel_or_404(request)
    return await map_response(request, parcel)


async def map_response(request: web.Request, parcel: Parcel) -> web.StreamResponse:
    png = await render_map(request, parcel)
    if png is None:
        raise web.HTTPNotFound(text="No mappable position yet")
    return web.Response(
        body=png, content_type="image/png", headers={"Cache-Control": "private, max-age=300"}
    )


async def render_map(request: web.Request, parcel: Parcel) -> bytes | None:
    """Route map PNG for a parcel, cached until the parcel changes."""
    bd = bot_data(request)
    geocoder, renderer = bd.get("geocoder"), bd.get("map_renderer")
    if geocoder is None or renderer is None:
        return None
    cache: OrderedDict[tuple[int, str, str], bytes | None] = request.app[MAP_CACHE]
    key = (parcel.user_id, parcel.tracking_number, str(parcel.last_change_at))
    if key in cache:
        cache.move_to_end(key)
        return cache[key]
    from parcel_tracker.maps.route import build_route_waypoints  # noqa: PLC0415
    from parcel_tracker.maps.transport import infer_transport_mode  # noqa: PLC0415

    history = await _repo(request).get_history(
        parcel.tracking_number, limit=50, user_id=parcel.user_id
    )
    waypoints = build_route_waypoints(history, geocoder)
    png: bytes | None = None
    if waypoints:
        mode = infer_transport_mode(parcel.carrier_name, parcel.last_event)
        try:
            png = await asyncio.to_thread(renderer.render_route, waypoints, mode=mode)
        except Exception:  # noqa: BLE001 — a map is decoration; never fail the page
            logger.warning("web map render failed", exc_info=True)
            return None
    cache[key] = png
    while len(cache) > _MAP_CACHE_SIZE:
        cache.popitem(last=False)
    return png


# --- import ----------------------------------------------------------------------


async def import_page(request: web.Request) -> web.StreamResponse:
    return await page(request, "import.html", {"report": None, "error": None})


async def import_submit(request: web.Request) -> web.StreamResponse:
    form = await request.post()
    upload = form.get("file")
    data = upload.file.read() if isinstance(upload, web.FileField) else b""
    if not data:
        return await page(request, "import.html", {"report": None, "error": "empty"}, status=400)
    try:
        report = await import_csv(
            _repo(request), user_id=user_id(request), data=data, max_active=_max_active(request)
        )
    except CsvImportError as exc:
        return await page(request, "import.html", {"report": None, "error": str(exc)}, status=400)
    return await page(request, "import.html", {"report": report, "error": None})


async def import_template(request: web.Request) -> web.StreamResponse:
    body = (
        "tracking_number,name,order_ref,recipient,destination,tags,notes\n"
        'RR123456785IT,Blue mug,#1001,Ada Lovelace,"Milano, IT",gift,Fragile\n'
    )
    return web.Response(
        body=body.encode("utf-8"),
        content_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="shipments-template.csv"'},
    )


# --- settings --------------------------------------------------------------------


async def settings_page(request: web.Request, *, new_token: str | None = None) -> web.Response:
    uid = user_id(request)
    bd = bot_data(request)
    return await page(
        request,
        "settings.html",
        {
            "seller_mode": await _settings(request).seller_mode(uid),
            "shop": await _settings(request).shop_name(uid) or "",
            "language": await bd["user_repo"].get_language(
                uid, default=bd["config"].default_language
            ),
            "languages": available_locales(LOCALE_DIR),
            "tokens": await web_repo(request).list_api_tokens(uid),
            "new_token": new_token,
            "api_base": f"{bd['config'].web_public_url}/api/v1",
        },
    )


async def settings_view(request: web.Request) -> web.StreamResponse:
    return await settings_page(request)


async def settings_save(request: web.Request) -> web.StreamResponse:
    form = await request.post()
    uid = user_id(request)
    await _settings(request).set_seller_mode(uid, form.get("seller_mode") == "on")
    shop = " ".join(str(form.get("shop_name") or "").split())[:_SHOP_NAME_MAX]
    await _settings(request).set_user(uid, SHOP_NAME, shop or None)
    language = str(form.get("language") or "")
    if language in available_locales(LOCALE_DIR):
        await bot_data(request)["user_repo"].set_language(uid, language)
    raise _redirect("/settings", msg="saved")


async def token_create(request: web.Request) -> web.StreamResponse:
    form = await request.post()
    name = " ".join(str(form.get("name") or "").split())[:_TOKEN_NAME_MAX] or "API"
    token = await web_repo(request).create_api_token(user_id(request), name)
    if token is None:
        raise _redirect("/settings", msg="token_limit")
    return await settings_page(request, new_token=token)


async def token_revoke(request: web.Request) -> web.StreamResponse:
    token_id = _int(request.match_info.get("token_id"), -1)
    await web_repo(request).revoke_api_token(user_id(request), token_id)
    raise _redirect("/settings", msg="token_revoked")


async def logout_everywhere(request: web.Request) -> web.StreamResponse:
    await web_repo(request).delete_sessions_for_user(user_id(request))
    from parcel_tracker.web.auth import clear_session_cookie  # noqa: PLC0415

    response = _redirect("/login", bye=1)
    clear_session_cookie(response)
    raise response


async def erase_account(request: web.Request) -> web.StreamResponse:
    form = await request.post()
    if form.get("confirm") != "on":
        raise _redirect("/settings", msg="confirm_needed")
    uid = session(request).user_id
    await bot_data(request)["user_repo"].erase_user_data(uid)
    logger.info("user %s erased their data from the web dashboard", uid)
    from parcel_tracker.web.auth import clear_session_cookie  # noqa: PLC0415

    response = _redirect("/login", bye=1)
    clear_session_cookie(response)
    raise response
