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


def test_load_from_directory_nonexistent_returns_zero(tmp_path: Path) -> None:
    """load_from_directory returns 0 when path does not exist (line 43)."""
    registry = TrackerRegistry()
    count = registry.load_from_directory(tmp_path / "does_not_exist")
    assert count == 0


def test_load_from_directory_skips_underscore_files(tmp_path: Path) -> None:
    """Files starting with '_' are skipped (line 48)."""
    (tmp_path / "_private.py").write_text("# ignored")
    registry = TrackerRegistry()
    count = registry.load_from_directory(tmp_path)
    assert count == 0


def test_load_from_directory_skips_syntax_error_file(tmp_path: Path) -> None:
    """Files with SyntaxError are skipped gracefully (lines 59-61)."""
    (tmp_path / "broken.py").write_text("def (: pass  # intentional syntax error")
    registry = TrackerRegistry()
    count = registry.load_from_directory(tmp_path)
    assert count == 0


def test_load_from_directory_skips_file_without_tracker_class(tmp_path: Path) -> None:
    """Files without a 'Tracker' attribute are skipped (lines 65-66)."""
    (tmp_path / "no_tracker.py").write_text("SOME_CONST = 42\n")
    registry = TrackerRegistry()
    count = registry.load_from_directory(tmp_path)
    assert count == 0


def test_load_from_directory_skips_tracker_not_subclass(tmp_path: Path) -> None:
    """Files where Tracker is not an AbstractTracker subclass are skipped (lines 68-72)."""
    (tmp_path / "wrong_base.py").write_text("class Tracker:\n    pass\n")
    registry = TrackerRegistry()
    count = registry.load_from_directory(tmp_path)
    assert count == 0


def test_load_from_directory_skips_duplicate_plugin(tmp_path: Path) -> None:
    """Duplicate plugin name (already registered) is skipped (lines 77-78)."""
    plugin_src = textwrap.dedent(
        """
        import re
        from parcel_tracker.core.tracker_base import AbstractTracker, TrackingResult
        from parcel_tracker.db.models import ShipmentStatus

        class Tracker(AbstractTracker):
            name = "dup_plugin"
            priority = 1
            tracking_id_patterns = [re.compile(r"^DUP\\d+$")]

            async def fetch(self, tracking_id):
                return TrackingResult(
                    tracking_number=tracking_id,
                    found=True,
                    status=ShipmentStatus.IN_TRANSIT,
                    carrier_name="Dup",
                )
        """
    )
    (tmp_path / "dup_a.py").write_text(plugin_src)
    (tmp_path / "dup_b.py").write_text(plugin_src)

    registry = TrackerRegistry()
    count = registry.load_from_directory(tmp_path)
    # Only one should load; the second duplicate is skipped
    assert count == 1
    assert registry.get_by_name("dup_plugin") is not None


def test_get_by_name_returns_none_for_unknown() -> None:
    """get_by_name returns None for an unregistered tracker."""
    registry = TrackerRegistry()
    assert registry.get_by_name("nonexistent") is None
