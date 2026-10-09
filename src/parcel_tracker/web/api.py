"""JSON API v1, authenticated with personal tokens (``Authorization: Bearer ptb_…``).

Meant for shop integrations: create a shipment when an order ships, read its
status back, archive it when done. Every call is scoped to the token's owner.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

from aiohttp import web

from parcel_tracker.core.shipments import (
    DETAIL_FIELDS_WEB,
    AddOutcome,
    ShipmentInput,
    add_shipment,
    clean_tags,
    clip_field,
    is_stalled,
    normalize_tracking_number,
    status_group,
)
from parcel_tracker.core.stats import compute_stats
from parcel_tracker.db.models import Parcel, TrackingEvent
from parcel_tracker.db.repository import ParcelRepository
from parcel_tracker.web.auth import bot_data
from parcel_tracker.web.keys import API_USER
from parcel_tracker.web.render import iso
from parcel_tracker.web.views import VIEWS, filter_parcels, share_url

_MAX_LIMIT = 500


def _uid(request: web.Request) -> int:
    return int(request[API_USER])


def _repo(request: web.Request) -> ParcelRepository:
    repo: ParcelRepository = bot_data(request)["parcel_repo"]
    return repo


def _stall_days(request: web.Request) -> int:
    return int(getattr(bot_data(request)["config"], "stall_alert_days", 0) or 0)


def serialize(request: web.Request, p: Parcel, *, now: datetime) -> dict[str, Any]:
    return {
        "id": p.id,
        "tracking_number": p.tracking_number,
        "name": p.name,
        "order_ref": p.order_ref,
        "recipient": p.recipient,
        "destination": p.destination,
        "notes": p.notes,
        "tags": p.tags,
        "carrier": p.carrier_name or p.carrier_code,
        "status": p.status.value,
        "status_group": status_group(p.status).value,
        "last_event": p.last_event,
        "last_event_time": p.last_event_time,
        "last_location": p.last_location,
        "active": p.is_active,
        "stalled": is_stalled(p, now, _stall_days(request)),
        "created_at": iso(p.created_at) or None,
        "delivered_at": iso(p.delivered_at) or None,
        "last_check_at": iso(p.last_check_at) or None,
        "last_change_at": iso(p.last_change_at) or None,
        "share_url": share_url(request, p.share_token),
    }


def _event(ev: TrackingEvent) -> dict[str, Any]:
    return {"time": ev.time, "description": ev.description, "location": ev.location}


def _int(raw: str | None, default: int) -> int:
    try:
        return int(raw) if raw is not None else default
    except ValueError:
        return default


async def _json_body(request: web.Request) -> dict[str, Any]:
    try:
        body = await request.json()
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise web.HTTPBadRequest(reason="body must be JSON") from exc
    if not isinstance(body, dict):
        raise web.HTTPBadRequest(reason="body must be a JSON object")
    return body


async def _find(request: web.Request) -> Parcel:
    code = normalize_tracking_number(request.match_info["tracking_number"])
    parcel = await _repo(request).get_for_user(code, user_id=_uid(request))
    if parcel is None:
        raise web.HTTPNotFound(reason="shipment not found")
    return parcel


async def list_shipments(request: web.Request) -> web.StreamResponse:
    now = datetime.now(UTC)
    view = request.query.get("view", "all")
    if view not in VIEWS:
        raise web.HTTPBadRequest(reason=f"view must be one of {', '.join(VIEWS)}")
    parcels = filter_parcels(
        await _repo(request).list_all_for_user(user_id=_uid(request)),
        view=view,
        query=request.query.get("q", "").strip()[:100],
        carrier=request.query.get("carrier", "").strip(),
        tag=request.query.get("tag", "").strip().lower(),
        now=now,
        stall_days=_stall_days(request),
    )
    limit = min(_MAX_LIMIT, max(1, _int(request.query.get("limit"), 100)))
    offset = max(0, _int(request.query.get("offset"), 0))
    return web.json_response(
        {
            "total": len(parcels),
            "limit": limit,
            "offset": offset,
            "shipments": [serialize(request, p, now=now) for p in parcels[offset : offset + limit]],
        }
    )


async def create_shipment(request: web.Request) -> web.StreamResponse:
    body = await _json_body(request)
    tags = body.get("tags")
    data = ShipmentInput(
        tracking_number=str(body.get("tracking_number") or ""),
        name=_opt(body.get("name")),
        order_ref=_opt(body.get("order_ref")),
        recipient=_opt(body.get("recipient")),
        destination=_opt(body.get("destination")),
        notes=_opt(body.get("notes")),
        tags=clean_tags(tags if isinstance(tags, list | str) else None),
    )
    config = bot_data(request)["config"]
    outcome, parcel = await add_shipment(
        _repo(request),
        user_id=_uid(request),
        data=data,
        max_active=int(getattr(config, "max_active_shipments", 0) or 0),
    )
    if outcome is AddOutcome.INVALID:
        return web.json_response({"error": "invalid tracking number"}, status=422)
    if outcome is AddOutcome.DUPLICATE:
        return web.json_response({"error": "already tracked"}, status=409)
    if outcome is AddOutcome.LIMIT:
        return web.json_response({"error": "active shipment limit reached"}, status=409)
    assert parcel is not None  # noqa: S101 — ADDED always returns the parcel
    return web.json_response(serialize(request, parcel, now=datetime.now(UTC)), status=201)


def _opt(value: object) -> str | None:
    return str(value) if value is not None and str(value).strip() else None


async def get_shipment(request: web.Request) -> web.StreamResponse:
    parcel = await _find(request)
    payload = serialize(request, parcel, now=datetime.now(UTC))
    if request.query.get("events") in ("1", "true"):
        events = await _repo(request).get_history(
            parcel.tracking_number, limit=200, user_id=parcel.user_id
        )
        payload["events"] = [_event(e) for e in events]
    return web.json_response(payload)


async def update_shipment(request: web.Request) -> web.StreamResponse:
    parcel = await _find(request)
    body = await _json_body(request)
    fields: dict[str, str | list[str] | None] = {}
    for key in DETAIL_FIELDS_WEB:
        if key in body:
            fields[key] = clip_field(key, _opt(body[key]))
    if "tags" in body:
        tags = body["tags"]
        fields["tags"] = clean_tags(tags if isinstance(tags, list | str) else None)
    await _repo(request).update_details(parcel.tracking_number, user_id=parcel.user_id, **fields)
    updated = await _repo(request).get_for_user(parcel.tracking_number, user_id=parcel.user_id)
    assert updated is not None  # noqa: S101
    return web.json_response(serialize(request, updated, now=datetime.now(UTC)))


async def delete_shipment(request: web.Request) -> web.StreamResponse:
    """Archive (stop tracking); ``?purge=1`` deletes the shipment and its history."""
    parcel = await _find(request)
    if request.query.get("purge") in ("1", "true"):
        await _repo(request).delete_for_user(parcel.tracking_number, user_id=parcel.user_id)
    else:
        await _repo(request).deactivate(parcel.tracking_number, user_id=parcel.user_id)
    return web.Response(status=204)


async def stats(request: web.Request) -> web.StreamResponse:
    now = datetime.now(UTC)
    parcels = await _repo(request).list_all_for_user(user_id=_uid(request))
    s = compute_stats(parcels, now=now, stall_days=_stall_days(request))
    return web.json_response(
        {
            "total": s.total,
            "active": s.active,
            "by_group": {g.value: n for g, n in s.by_group.items()},
            "attention": s.attention,
            "stalled": s.stalled,
            "shipped_last_30_days": s.shipped_recent,
            "delivered_last_30_days": s.delivered_recent,
            "median_delivery_days": s.median_delivery_days,
            "p90_delivery_days": s.p90_delivery_days,
            "delivery_rate": s.delivery_rate,
            "carriers": [
                {
                    "carrier": c.carrier,
                    "total": c.total,
                    "delivered": c.delivered,
                    "issues": c.issues,
                    "median_days": c.median_days,
                }
                for c in s.carriers
            ],
        }
    )
