#!/usr/bin/env python3
"""Run the web dashboard on a demo database (no Telegram, no carriers needed).

    python scripts/demo_web.py [--port 8080] [--db /tmp/demo.db] [--lang en]

Seeds a small shop with shipments spread over twelve weeks, prints a one-time
login link, and serves the dashboard until interrupted. Used for the README
screenshots and to try the dashboard before connecting a bot.
"""

from __future__ import annotations

import argparse
import asyncio
import random
import tempfile
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import aiosqlite

from parcel_tracker.core.detector import CourierDetector
from parcel_tracker.core.registry import TrackerRegistry
from parcel_tracker.db.migrations import init_schema
from parcel_tracker.db.models import Parcel, ShipmentStatus, TrackingEvent
from parcel_tracker.db.repository import ParcelRepository, UserRepository, sql_ts
from parcel_tracker.db.settings_repository import SHOP_NAME, SettingsRepository
from parcel_tracker.db.web_repository import WebRepository
from parcel_tracker.web.server import WebServer

OWNER = 1
PRODUCTS = [
    "Ceramic mug",
    "Linen tote",
    "Desk lamp",
    "Wool scarf",
    "Notebook set",
    "Oak cutting board",
    "Scented candle",
    "Leather wallet",
    "Tea sampler",
    "Print A3",
    "Pottery bowl",
    "Silk scarf",
    "Espresso cups",
    "Recycled bag",
    "Brass keyring",
    "Herb kit",
]
CUSTOMERS = [
    ("Ada Lovelace", "Milano, IT"),
    ("Grace Hopper", "Roma, IT"),
    ("Alan Turing", "London, GB"),
    ("Katherine Johnson", "Paris, FR"),
    ("Hedy Lamarr", "Wien, AT"),
    ("Margaret Hamilton", "Berlin, DE"),
    ("Linus Pauling", "Madrid, ES"),
    ("Rosalind Franklin", "Amsterdam, NL"),
    ("Tim Berners-Lee", "Genève, CH"),
    ("Barbara Liskov", "Bologna, IT"),
    ("Edsger Dijkstra", "Rotterdam, NL"),
    ("Mary Somerville", "Edinburgh, GB"),
]
CARRIERS = [
    ("RR{n:08d}{c}IT", "Poste Italiane", ["Bologna, IT", "Milano, IT"]),
    ("1Z999AA1{n:010d}", "UPS", ["Köln, DE", "Milano, IT"]),
    ("JD0146{n:014d}", "DHL Express", ["Leipzig, DE", "Bergamo, IT"]),
    ("CP{n:08d}{c}DE", "DHL Paket", ["Leipzig, DE", "Wien, AT"]),
    ("LX{n:08d}{c}CN", "China Post", ["Shanghai, CN", "Frankfurt, DE"]),
    ("{n:012d}", "BRT", ["Bologna, IT", "Firenze, IT"]),
]


def _s10(template: str, n: int) -> str:
    from parcel_tracker.core.shipments import s10_check_digit

    serial = f"{n:08d}"
    return (
        template.format(n=n, c=s10_check_digit(serial))
        if "{c}" in template
        else template.format(n=n)
    )


async def seed(db: str, *, shipments: int = 32, seed_value: int = 7) -> None:
    rng = random.Random(seed_value)
    repo = ParcelRepository(db)
    settings = SettingsRepository(db)
    await settings.set_seller_mode(OWNER, True)
    await settings.set_user(OWNER, SHOP_NAME, "Bottega Aurora")
    now = datetime.now(UTC).replace(microsecond=0)
    for i in range(shipments):
        template, carrier, route = CARRIERS[i % len(CARRIERS)]
        code = _s10(template, 10_000_000 + i * 7919)
        customer, city = CUSTOMERS[i % len(CUSTOMERS)]
        age = rng.uniform(0.2, 80) if i > 6 else rng.uniform(0.3, 4)
        if i == 3:
            age = 13  # a stalled one
        delivered_after = rng.uniform(1.5, 6.5) if age > 7 and i % 9 != 4 and i != 3 else None
        if delivered_after is not None:
            status = ShipmentStatus.DELIVERED
        elif i == 3:
            status = ShipmentStatus.IN_TRANSIT
        elif i % 9 == 4:
            status = rng.choice([ShipmentStatus.EXCEPTION, ShipmentStatus.RETURNED])
        else:
            status = [
                ShipmentStatus.INFO_RECEIVED,
                ShipmentStatus.IN_TRANSIT,
                ShipmentStatus.OUT_FOR_DELIVERY,
            ][i % 3]
        parcel = Parcel(
            tracking_number=code,
            user_id=OWNER,
            name=PRODUCTS[i % len(PRODUCTS)],
            order_ref=f"#{1100 + i}",
            recipient=customer,
            destination=city,
            tags=["express"] if i % 5 == 0 else (["gift"] if i % 7 == 0 else []),
        )
        await repo.create(parcel)
        created = now - timedelta(days=age)
        events = [
            TrackingEvent(
                time=(created + timedelta(hours=6)).isoformat(),
                description="Shipment information received",
                location=route[0],
            ),
            TrackingEvent(
                time=(created + timedelta(hours=20)).isoformat(),
                description="Picked up by the carrier",
                location=route[0],
            ),
        ]
        if status is not ShipmentStatus.INFO_RECEIVED:
            events.append(
                TrackingEvent(
                    time=(created + timedelta(days=1, hours=8)).isoformat(),
                    description="Departed sorting facility",
                    location=route[0],
                )
            )
            events.append(
                TrackingEvent(
                    time=(created + timedelta(days=min(age, 2), hours=2)).isoformat(),
                    description="Arrived at destination hub",
                    location=route[1],
                )
            )
        if status is ShipmentStatus.OUT_FOR_DELIVERY:
            events.append(
                TrackingEvent(
                    time=(now - timedelta(hours=2)).isoformat(),
                    description="Out for delivery",
                    location=city,
                )
            )
        if status is ShipmentStatus.EXCEPTION:
            events.append(
                TrackingEvent(
                    time=(now - timedelta(hours=20)).isoformat(),
                    description="Delivery exception: address incomplete",
                    location=city,
                )
            )
        if status is ShipmentStatus.RETURNED:
            events.append(
                TrackingEvent(
                    time=(now - timedelta(days=1)).isoformat(),
                    description="Returned to sender",
                    location=route[0],
                )
            )
        if delivered_after is not None:
            events.append(
                TrackingEvent(
                    time=(created + timedelta(days=delivered_after)).isoformat(),
                    description="Delivered",
                    location=city,
                )
            )
        if status is ShipmentStatus.INFO_RECEIVED:
            events = events[:1]
        events = [e for e in events if e.time <= now.isoformat()]
        await repo.add_events_dedup(code, events, user_id=OWNER)
        last = max(events, key=lambda e: e.time)
        await repo.update_latest(code, last.description, last.time, last.location, user_id=OWNER)
        await repo.update_carrier(code, None, carrier, user_id=OWNER)
        await repo.update_status(code, status, user_id=OWNER)
        last_change = datetime.fromisoformat(last.time)
        async with aiosqlite.connect(db) as conn:
            await conn.execute(
                "UPDATE parcels SET created_at = ?, last_change_at = ?, last_check_at = ? WHERE tracking_number = ?",
                (
                    sql_ts(created),
                    sql_ts(last_change),
                    (now - timedelta(minutes=rng.randint(2, 40))).isoformat(),
                    code,
                ),
            )
            if delivered_after is not None:
                await conn.execute(
                    "UPDATE parcels SET delivered_at = ?, is_active = 0 WHERE tracking_number = ?",
                    (sql_ts(created + timedelta(days=delivered_after)), code),
                )
            await conn.commit()
        if i == 0:
            await repo.set_share_token(code, user_id=OWNER, token="demo-share-link")


def demo_bot_data(db: str, *, port: int, lang: str, maps: bool) -> dict[str, Any]:
    config = SimpleNamespace(
        owner_id=OWNER,
        allowed_user_ids=[],
        admin_user_ids=frozenset(),
        default_language=lang,
        stall_alert_days=7,
        max_active_shipments=0,
        web_public_url=f"http://localhost:{port}",
        web_session_days=30,
        batch_size=10,
        status_interval_overrides={},
    )
    geocoder = renderer = None
    if maps:
        from parcel_tracker.maps.geocoder import Geocoder
        from parcel_tracker.maps.renderer import MapRenderer

        root = Path(__file__).resolve().parent.parent / "src" / "parcel_tracker" / "maps" / "data"
        geocoder = Geocoder(dataset_path=root / "cities1000.tsv")
        renderer = MapRenderer(
            user_agent="parcel-tracker-bot demo (+https://github.com/bernalli/parcel-tracker-bot)"
        )
    return {
        "config": config,
        "parcel_repo": ParcelRepository(db),
        "user_repo": UserRepository(db),
        "web_repo": WebRepository(db),
        "settings": SettingsRepository(db),
        "detector": CourierDetector(TrackerRegistry()),
        "geocoder": geocoder,
        "map_renderer": renderer,
    }


async def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8080)
    parser.add_argument("--db", default=str(Path(tempfile.gettempdir()) / "parcel-tracker-demo.db"))
    parser.add_argument("--lang", default="en")
    parser.add_argument(
        "--maps", action="store_true", help="render route maps (downloads map tiles)"
    )
    args = parser.parse_args()
    Path(args.db).unlink(missing_ok=True)
    await init_schema(args.db)
    await seed(args.db)
    await UserRepository(args.db).set_language(OWNER, args.lang)
    bot_data = demo_bot_data(args.db, port=args.port, lang=args.lang, maps=args.maps)
    server = WebServer(bot_data, host="127.0.0.1", port=args.port)
    await server.start()
    token = await bot_data["web_repo"].create_login_token(OWNER)
    print(f"LOGIN http://localhost:{args.port}/login?t={token}", flush=True)
    try:
        await asyncio.Event().wait()
    finally:
        await server.stop()


if __name__ == "__main__":
    asyncio.run(main())
