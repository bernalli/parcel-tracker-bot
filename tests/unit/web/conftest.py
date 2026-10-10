"""Fixtures for the web dashboard: a seeded database and an aiohttp test client."""

from __future__ import annotations

import re
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import aiosqlite
import pytest
from aiohttp.test_utils import TestClient, TestServer

from parcel_tracker.core.detector import CourierDetector
from parcel_tracker.core.registry import TrackerRegistry
from parcel_tracker.db.migrations import init_schema
from parcel_tracker.db.models import Parcel, ShipmentStatus, TrackingEvent
from parcel_tracker.db.repository import ParcelRepository, UserRepository, sql_ts
from parcel_tracker.db.settings_repository import SettingsRepository
from parcel_tracker.db.web_repository import WebRepository
from parcel_tracker.web.server import create_app

OWNER = 1
STRANGER = 99


async def seed(db: str) -> None:
    """A small realistic shop: in transit, out for delivery, stalled, problem, delivered."""
    repo = ParcelRepository(db)
    now = datetime.now(UTC)
    rows: list[tuple[Parcel, ShipmentStatus, float, float | None, list[str]]] = [
        (
            Parcel(
                tracking_number="1Z999AA10123456784",
                user_id=OWNER,
                name="Ceramic mug",
                order_ref="#1042",
                recipient="Ada Lovelace",
                destination="Milano, IT",
                tags=["gift"],
                carrier_name="UPS",
            ),
            ShipmentStatus.OUT_FOR_DELIVERY,
            2,
            None,
            ["Out for delivery"],
        ),
        (
            Parcel(
                tracking_number="RR123456785IT",
                user_id=OWNER,
                name="Linen tote",
                order_ref="#1043",
                recipient="Grace Hopper",
                destination="Roma, IT",
                carrier_name="Poste Italiane",
            ),
            ShipmentStatus.IN_TRANSIT,
            3,
            None,
            ["Accepted", "In transit"],
        ),
        (
            Parcel(
                tracking_number="LX987654321CN",
                user_id=OWNER,
                name="Desk lamp",
                order_ref="#1031",
                recipient="Alan Turing",
                carrier_name="China Post",
            ),
            ShipmentStatus.IN_TRANSIT,
            12,
            None,
            ["Departed origin"],
        ),
        (
            Parcel(
                tracking_number="JD014600006281234567",
                user_id=OWNER,
                name="Notebook set",
                order_ref="#1038",
                recipient="Katherine Johnson",
                carrier_name="DHL Express",
            ),
            ShipmentStatus.EXCEPTION,
            6,
            None,
            ["Address problem"],
        ),
        (
            Parcel(
                tracking_number="CP123456789DE",
                user_id=OWNER,
                name="Wool scarf",
                order_ref="#1020",
                recipient="Hedy Lamarr",
                carrier_name="DHL Paket",
            ),
            ShipmentStatus.DELIVERED,
            9,
            3.5,
            ["Delivered"],
        ),
    ]
    for parcel, status, age_days, delivered_after, events in rows:
        created = await repo.create(parcel)
        assert created is not None
        await repo.update_status(parcel.tracking_number, status, user_id=OWNER)
        await repo.add_events_dedup(
            parcel.tracking_number,
            [
                TrackingEvent(
                    time=(now - timedelta(days=age_days - i)).isoformat(),
                    description=d,
                    location="Bologna, IT",
                )
                for i, d in enumerate(events)
            ],
            user_id=OWNER,
        )
        await repo.update_latest(
            parcel.tracking_number, events[-1], now.isoformat(), "Bologna, IT", user_id=OWNER
        )
        async with aiosqlite.connect(db) as conn:
            created_at = now - timedelta(days=age_days)
            await conn.execute(
                "UPDATE parcels SET created_at = ?, last_change_at = ?, carrier_name = ? WHERE tracking_number = ?",
                (
                    sql_ts(created_at),
                    sql_ts(created_at if age_days > 10 else now - timedelta(hours=3)),
                    parcel.carrier_name,
                    parcel.tracking_number,
                ),
            )
            if delivered_after is not None:
                await conn.execute(
                    "UPDATE parcels SET delivered_at = ?, is_active = 0 WHERE tracking_number = ?",
                    (sql_ts(created_at + timedelta(days=delivered_after)), parcel.tracking_number),
                )
            await conn.commit()


@pytest.fixture
async def env(tmp_path: Path) -> AsyncIterator[SimpleNamespace]:
    db = str(tmp_path / "web.db")
    await init_schema(db)
    await seed(db)
    config = SimpleNamespace(
        owner_id=OWNER,
        allowed_user_ids=[],
        admin_user_ids=frozenset(),
        default_language="en",
        stall_alert_days=7,
        max_active_shipments=50,
        web_public_url="http://testserver",
        web_session_days=30,
        batch_size=10,
        status_interval_overrides={},
    )
    bot_data: dict[str, Any] = {
        "config": config,
        "parcel_repo": ParcelRepository(db),
        "user_repo": UserRepository(db),
        "web_repo": WebRepository(db),
        "settings": SettingsRepository(db),
        "detector": CourierDetector(TrackerRegistry()),
        "geocoder": None,
        "map_renderer": None,
    }
    client = TestClient(TestServer(create_app(bot_data)))
    await client.start_server()
    try:
        yield SimpleNamespace(client=client, bot_data=bot_data, db=db, config=config)
    finally:
        await client.close()


async def login(env: SimpleNamespace, user_id: int = OWNER) -> str:
    """Sign in through the real login flow; returns the CSRF token."""
    token = await env.bot_data["web_repo"].create_login_token(user_id)
    resp = await env.client.post("/login", data={"t": token}, allow_redirects=False)
    assert resp.status == 303, await resp.text()
    page = await env.client.get("/settings")
    html = await page.text()
    match = re.search(r'name="csrf" value="([^"]+)"', html)
    assert match, "csrf token not found"
    return match.group(1)
