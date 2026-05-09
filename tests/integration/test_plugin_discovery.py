"""Integration test: plugins/ directory is auto-loaded at startup."""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest


@pytest.mark.asyncio
async def test_plugin_directory_loads_demo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    plugins_dir = tmp_path / "plugins"
    plugins_dir.mkdir()
    demo_plugin = plugins_dir / "demo_xx.py"
    demo_plugin.write_text(
        textwrap.dedent(
            """
            import re
            from parcel_tracker.core.tracker_base import AbstractTracker, TrackingResult
            from parcel_tracker.db.models import ShipmentStatus

            class Tracker(AbstractTracker):
                name = "demo_xx"
                priority = 99
                tracking_id_patterns = [re.compile(r"^DEMO_XX\\d+$")]

                async def fetch(self, tracking_id):
                    return TrackingResult(
                        tracking_number=tracking_id,
                        found=True,
                        status=ShipmentStatus.IN_TRANSIT,
                    )
            """
        )
    )

    db_path = tmp_path / "data" / "test.db"
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "fake")
    monkeypatch.setenv("OWNER_ID", "1")
    monkeypatch.setenv("DATABASE_PATH", str(db_path))

    from parcel_tracker.config import Config
    from parcel_tracker.core.registry import TrackerRegistry
    from parcel_tracker.db.migrations import init_schema
    from parcel_tracker.trackers import register_builtins

    await init_schema(str(db_path))
    config = Config.from_env(load_dotenv_file=False)

    registry = TrackerRegistry()
    register_builtins(registry, config)
    loaded = registry.load_from_directory(plugins_dir)

    assert loaded == 1
    assert registry.get_by_name("demo_xx") is not None
