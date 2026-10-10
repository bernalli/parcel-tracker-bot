"""Regression tests for the core audit fixes (health, status guard, races, config)."""

from __future__ import annotations

import re
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import httpx
import pytest
from telegram.error import Forbidden

from parcel_tracker.config import Config, ConfigError
from parcel_tracker.core.detector import CourierDetector
from parcel_tracker.core.health import HealthManager, QuarantineThresholds
from parcel_tracker.core.http_client import _redirect_problem
from parcel_tracker.core.rate_limiter import RateLimiter
from parcel_tracker.core.registry import TrackerRegistry
from parcel_tracker.core.scheduler import check_parcel_now, check_updates
from parcel_tracker.core.tracker_base import AbstractTracker, TrackingResult
from parcel_tracker.db.health_repository import HealthRepository
from parcel_tracker.db.migrations import init_schema
from parcel_tracker.db.models import Parcel, ShipmentStatus, TrackingEvent
from parcel_tracker.db.repository import ParcelRepository, UserRepository

NOW = datetime(2026, 10, 9, 12, 0, tzinfo=UTC)
THRESHOLDS = QuarantineThresholds(3, 1, 6, 6, 12, 24)


class _Tracker(AbstractTracker):
    name = "fake"
    priority = 50
    tracking_id_patterns = [re.compile(r"^FAKE\d+$")]

    def __init__(self) -> None:
        self.results: dict[str, TrackingResult] = {}
        self.on_fetch: Any = None

    async def fetch(self, tracking_id: str) -> TrackingResult:
        if self.on_fetch is not None:
            await self.on_fetch()
        return self.results.get(
            tracking_id, TrackingResult(tracking_number=tracking_id, found=False)
        )


class _Notifier:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, Any]]] = []
        self.fail_with: BaseException | None = None

    def __getattr__(self, name: str) -> Any:
        async def record(**kwargs: Any) -> None:
            if self.fail_with is not None:
                raise self.fail_with
            self.calls.append((name, kwargs))

        return record


async def _env(tmp_path: Path) -> SimpleNamespace:
    db = str(tmp_path / "bot.db")
    await init_schema(db)
    registry = TrackerRegistry()
    tracker = _Tracker()
    registry.register(tracker)
    repo = ParcelRepository(db)
    health = HealthManager(HealthRepository(db), thresholds=THRESHOLDS)
    notifier = _Notifier()
    config = SimpleNamespace(
        owner_id=1,
        allowed_user_ids=[],
        admin_user_ids=frozenset(),
        batch_size=10,
        status_interval_overrides={},
        data_retention_days=0,
        stall_alert_days=0,
    )
    bot_data: dict[str, Any] = {
        "config": config,
        "parcel_repo": repo,
        "user_repo": UserRepository(db),
        "registry": registry,
        "detector": CourierDetector(registry),
        "health": health,
        "notifier": notifier,
        "rate_limiter": RateLimiter(default_rate_per_min=6000),
        "now": lambda: NOW,
    }
    return SimpleNamespace(
        ctx=SimpleNamespace(bot_data=bot_data),
        repo=repo,
        tracker=tracker,
        notifier=notifier,
        health=health,
        db=db,
    )


def _found(code: str, status: ShipmentStatus, *events: str) -> TrackingResult:
    return TrackingResult(
        tracking_number=code,
        found=True,
        status=status,
        last_event=events[-1] if events else None,
        events=[
            TrackingEvent(time=f"2026-10-0{i + 1}T10:00:00Z", description=e)
            for i, e in enumerate(events)
        ],
    )


async def test_not_found_codes_never_quarantine_the_tracker(tmp_path) -> None:
    env = await _env(tmp_path)
    for i in range(30):
        for _ in range(3):
            await env.health.record_not_found("fake", f"FAKE{i}")
    assert not await env.health.is_tracker_quarantined("fake")
    assert await env.health.is_quarantined("fake", "FAKE0")  # per-code back-off still applies
    state = await env.health.repo.get_state("fake", "FAKE0")
    assert state is not None
    assert state.quarantine_until is not None
    # Capped at the first tier (1h) however often the code is missing.
    for _ in range(20):
        await env.health.record_not_found("fake", "FAKE0")
    state = await env.health.repo.get_state("fake", "FAKE0")
    assert state is not None and state.quarantine_until is not None
    assert state.quarantine_until - datetime.now(UTC) <= timedelta(hours=1, minutes=1)


async def test_count_quarantined_ignores_single_codes(tmp_path) -> None:
    env = await _env(tmp_path)
    for _ in range(3):
        await env.health.record_not_found("fake", "FAKE1")
    assert await env.health.repo.count_quarantined() == 0


async def test_prune_orphans_drops_codes_of_gone_parcels(tmp_path) -> None:
    env = await _env(tmp_path)
    await env.repo.create(Parcel(tracking_number="FAKE1", user_id=1))
    await env.health.record_success("fake", "FAKE1")
    await env.health.record_success("fake", "FAKE2")  # no parcel tracks it
    assert await env.health.repo.prune_orphans() == 1
    assert await env.health.repo.get_state("fake", "FAKE1") is not None
    assert await env.health.repo.get_state("fake", "") is not None


async def test_readding_a_delivered_parcel_resumes_polling(tmp_path) -> None:
    env = await _env(tmp_path)
    await env.repo.create(Parcel(tracking_number="FAKE1", user_id=1))
    await env.repo.set_delivered("FAKE1", NOW, user_id=1)
    await env.repo.deactivate("FAKE1", user_id=1)
    again = await env.repo.create(Parcel(tracking_number="FAKE1", user_id=1))
    assert again is not None
    assert again.status is ShipmentStatus.NOT_FOUND
    assert again.last_check_at is None
    env.tracker.results["FAKE1"] = _found("FAKE1", ShipmentStatus.IN_TRANSIT, "Picked up")
    await check_updates(env.ctx)
    parcel = await env.repo.get_for_user("FAKE1", user_id=1)
    assert parcel is not None and parcel.status is ShipmentStatus.IN_TRANSIT


async def test_not_found_result_never_overwrites_known_status(tmp_path) -> None:
    env = await _env(tmp_path)
    await env.repo.create(Parcel(tracking_number="FAKE1", user_id=1))
    await env.repo.update_status("FAKE1", ShipmentStatus.OUT_FOR_DELIVERY, user_id=1)
    env.tracker.results["FAKE1"] = TrackingResult(
        tracking_number="FAKE1", found=True, status=ShipmentStatus.NOT_FOUND
    )
    await check_updates(env.ctx)
    parcel = await env.repo.get_for_user("FAKE1", user_id=1)
    assert parcel is not None and parcel.status is ShipmentStatus.OUT_FOR_DELIVERY


async def test_delivered_is_not_reopened_without_new_events(tmp_path) -> None:
    env = await _env(tmp_path)
    await env.repo.create(Parcel(tracking_number="FAKE1", user_id=1))
    env.tracker.results["FAKE1"] = _found("FAKE1", ShipmentStatus.DELIVERED, "Delivered")
    await check_parcel_now(env.ctx.bot_data, user_id=1, tracking_number="FAKE1")
    prompts = [n for n, _ in env.notifier.calls if n == "send_delivery_confirmation"]
    assert len(prompts) == 1
    # A lagging source reports In transit with the same (already stored) events.
    lagging = _found("FAKE1", ShipmentStatus.IN_TRANSIT, "Delivered")
    env.tracker.results["FAKE1"] = lagging
    await check_parcel_now(env.ctx.bot_data, user_id=1, tracking_number="FAKE1")
    parcel = await env.repo.get_for_user("FAKE1", user_id=1)
    assert parcel is not None and parcel.status is ShipmentStatus.DELIVERED


async def test_parcel_removed_during_fetch_is_left_alone(tmp_path) -> None:
    env = await _env(tmp_path)
    await env.repo.create(Parcel(tracking_number="FAKE1", user_id=1))
    env.tracker.results["FAKE1"] = _found("FAKE1", ShipmentStatus.IN_TRANSIT, "Moving")

    async def erase() -> None:
        await UserRepository(env.db).erase_user_data(1)

    env.tracker.on_fetch = erase
    await check_updates(env.ctx)
    assert env.notifier.calls == []
    assert await env.repo.get_history("FAKE1", user_id=1) == []


async def test_status_only_change_is_retried_after_failed_send(tmp_path) -> None:
    env = await _env(tmp_path)
    await env.repo.create(Parcel(tracking_number="FAKE1", user_id=1))
    env.tracker.results["FAKE1"] = _found("FAKE1", ShipmentStatus.IN_TRANSIT, "Moving")
    await check_updates(env.ctx)
    # Status moves to Alert with no new event, and Telegram fails.
    env.tracker.results["FAKE1"] = _found("FAKE1", ShipmentStatus.ALERT, "Moving")
    env.notifier.fail_with = RuntimeError("429")
    await check_parcel_now(env.ctx.bot_data, user_id=1, tracking_number="FAKE1")  # no notify
    parcel = await env.repo.get_for_user("FAKE1", user_id=1)
    assert parcel is not None
    # check_parcel_now does not notify, so it stores the status straight away;
    # the periodic path is what must defer. Reset and exercise it.
    await env.repo.update_status("FAKE1", ShipmentStatus.IN_TRANSIT, user_id=1)
    await env.repo.set_last_check_at("FAKE1", NOW - timedelta(days=1), user_id=1)
    with pytest.raises(RuntimeError):
        from parcel_tracker.core import scheduler

        listed = await env.repo.get_for_user("FAKE1", user_id=1)
        assert listed is not None
        await scheduler._check_one(
            parcel=listed,
            user_id=1,
            parcel_repo=env.repo,
            detector=env.ctx.bot_data["detector"],
            health=env.health,
            notifier=env.notifier,
            rate_limiter=env.ctx.bot_data["rate_limiter"],
            prefs=None,
            now=lambda: NOW,
        )
    parcel = await env.repo.get_for_user("FAKE1", user_id=1)
    assert parcel is not None and parcel.status is ShipmentStatus.IN_TRANSIT  # not lost
    env.notifier.fail_with = None
    await env.repo.set_last_check_at("FAKE1", NOW - timedelta(days=1), user_id=1)
    await check_updates(env.ctx)
    parcel = await env.repo.get_for_user("FAKE1", user_id=1)
    assert parcel is not None and parcel.status is ShipmentStatus.ALERT
    assert any(kw.get("new_status") is ShipmentStatus.ALERT for _n, kw in env.notifier.calls)


async def test_blocked_user_does_not_retry_forever(tmp_path) -> None:
    env = await _env(tmp_path)
    await env.repo.create(Parcel(tracking_number="FAKE1", user_id=1))
    env.tracker.results["FAKE1"] = _found("FAKE1", ShipmentStatus.IN_TRANSIT, "Moving")
    env.notifier.fail_with = Forbidden("bot was blocked by the user")
    await check_updates(env.ctx)
    assert await env.repo.get_unnotified("FAKE1", user_id=1) == []


async def test_history_is_ordered_by_event_time(tmp_path) -> None:
    env = await _env(tmp_path)
    await env.repo.create(Parcel(tracking_number="FAKE1", user_id=1))
    events = [
        TrackingEvent(time="2026-10-03T10:00:00Z", description="third"),
        TrackingEvent(time="2026-10-01T10:00:00Z", description="first"),
        TrackingEvent(time="2026-10-02T10:00:00Z", description="second"),
    ]
    await env.repo.add_events_dedup("FAKE1", events, user_id=1)
    history = await env.repo.get_history("FAKE1", user_id=1, limit=2)
    assert [e.description for e in history] == ["third", "second"]


@pytest.mark.parametrize(
    ("env_name", "value"),
    [
        ("BATCH_SIZE", "0"),
        ("RATE_LIMIT_DEFAULT_PER_MIN", "0"),
        ("CHECK_INTERVAL_MINUTES", "0"),
        ("METRICS_PORT", "99999"),
        ("STATUS_INTERVAL_IN_TRANSIT", "-1"),
        ("RATE_LIMIT_TRACKER_DHL", "0"),
        ("WEB_PUBLIC_URL", "parcels.example.com"),
    ],
)
def test_invalid_config_values_are_rejected(monkeypatch, env_name: str, value: str) -> None:
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "t")
    monkeypatch.setenv("OWNER_ID", "1")
    monkeypatch.setenv(env_name, value)
    with pytest.raises(ConfigError):
        Config.from_env(load_dotenv_file=False)


@pytest.mark.parametrize(
    "host", ["127.1", "2130706433", "0x7f.0.0.1", "10.0.0.1", "[::1]", "169.254.169.254"]
)
def test_redirect_guard_rejects_loopback_shorthands(host: str) -> None:
    problem = _redirect_problem(httpx.URL("https://carrier.test/"), httpx.URL(f"https://{host}/x"))
    assert problem == "non-public address"


def test_redirect_guard_allows_public_hosts() -> None:
    assert _redirect_problem(httpx.URL("https://a.test/"), httpx.URL("https://b.test/x")) is None
    assert _redirect_problem(httpx.URL("https://a.test/"), httpx.URL("https://8.8.8.8/x")) is None


def test_plugin_with_dataclass_loads(tmp_path) -> None:
    plugin = tmp_path / "acme.py"
    plugin.write_text(
        "from __future__ import annotations\n"
        "import re\n"
        "from dataclasses import dataclass\n"
        "from parcel_tracker.core.tracker_base import AbstractTracker, TrackingResult\n"
        "@dataclass\n"
        "class Options:\n"
        "    depth: int = 1\n"
        "class Tracker(AbstractTracker):\n"
        "    name = 'acme_dc'\n"
        "    tracking_id_patterns = [re.compile(r'^ACME\\d+$')]\n"
        "    def __init__(self, *, http_client=None):\n"
        "        self.http_client = http_client\n"
        "    async def fetch(self, tracking_id):\n"
        "        return TrackingResult(tracking_number=tracking_id, found=False)\n"
    )
    registry = TrackerRegistry()
    sentinel = object()
    assert registry.load_from_directory(tmp_path, inject={"http_client": sentinel, "x": 1}) == 1
    tracker = registry.get_by_name("acme_dc")
    assert tracker is not None
    assert tracker.http_client is sentinel  # type: ignore[attr-defined]


def test_geocoder_state_codes(tmp_path) -> None:
    from parcel_tracker.maps.geocoder import Geocoder

    data = tmp_path / "cities.tsv"
    data.write_text(
        "Toronto\tToronto\t\t43.7\t-79.4\tCA\n"
        "Berlin\tBerlin\t\t52.5\t13.4\tDE\n"
        "Sacramento\tSacramento\t\t38.6\t-121.5\tUS\n"
        "Toronto\tToronto\t\t40.5\t-80.6\tUS\n"
        "Berlin\tBerlin\t\t40.9\t-81.4\tUS\n"
    )
    g = Geocoder(dataset_path=data)
    assert g.geocode("Toronto, CA") == (43.7, -79.4)
    assert g.geocode("Berlin, DE") == (52.5, 13.4)
    assert g.geocode("SACRAMENTO, CA") == (38.6, -121.5)
    assert g.geocode("Toronto, OH, US") == (40.5, -80.6)
