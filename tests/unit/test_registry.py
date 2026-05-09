"""Tests for core.registry — plugin discovery."""

from __future__ import annotations

import re
import textwrap
from pathlib import Path

import pytest

from parcel_tracker.core.registry import TrackerRegistry
from parcel_tracker.core.tracker_base import AbstractTracker, TrackingResult
from parcel_tracker.db.models import ShipmentStatus


class _BuiltinTracker(AbstractTracker):
    name = "builtin"
    priority = 50
    tracking_id_patterns = [re.compile(r"^BLT\d+$")]

    async def fetch(self, tracking_id: str) -> TrackingResult:
        return TrackingResult(
            tracking_number=tracking_id,
            found=True,
            status=ShipmentStatus.IN_TRANSIT,
            carrier_name="Builtin",
        )


def test_register_and_get_by_name() -> None:
    registry = TrackerRegistry()
    registry.register(_BuiltinTracker())
    tracker = registry.get_by_name("builtin")
    assert tracker is not None
    assert tracker.name == "builtin"


def test_register_duplicate_raises() -> None:
    registry = TrackerRegistry()
    registry.register(_BuiltinTracker())
    with pytest.raises(ValueError, match="already registered"):
        registry.register(_BuiltinTracker())


def test_iter_all_returns_registered() -> None:
    registry = TrackerRegistry()
    registry.register(_BuiltinTracker())
    names = [t.name for t in registry.iter_all()]
    assert "builtin" in names


def test_load_from_directory(tmp_path: Path) -> None:
    plugin_file = tmp_path / "demo.py"
    plugin_file.write_text(
        textwrap.dedent(
            """
            import re
            from parcel_tracker.core.tracker_base import AbstractTracker, TrackingResult
            from parcel_tracker.db.models import ShipmentStatus

            class Tracker(AbstractTracker):
                name = "demo_plugin"
                priority = 99
                tracking_id_patterns = [re.compile(r"^DEMO\\d+$")]

                async def fetch(self, tracking_id):
                    return TrackingResult(
                        tracking_number=tracking_id,
                        found=True,
                        status=ShipmentStatus.IN_TRANSIT,
                        carrier_name="Demo Plugin",
                    )
            """
        )
    )

    registry = TrackerRegistry()
    registry.load_from_directory(tmp_path)
    tracker = registry.get_by_name("demo_plugin")
    assert tracker is not None
    assert tracker.priority == 99
