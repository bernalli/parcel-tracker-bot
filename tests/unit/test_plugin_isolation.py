from __future__ import annotations

import re
from pathlib import Path

from parcel_tracker.core.registry import TrackerRegistry

GOOD = """
import re
from parcel_tracker.core.tracker_base import AbstractTracker, TrackingResult

class Tracker(AbstractTracker):
    name = "good_plugin"
    priority = 10
    tracking_id_patterns = [re.compile(r"^GOOD\\\\d+$")]

    async def fetch(self, tracking_id):
        return TrackingResult(tracking_number=tracking_id, found=False)
"""


def test_broken_plugins_do_not_stop_loading(tmp_path: Path) -> None:
    (tmp_path / "a_runtime_error.py").write_text("raise RuntimeError('boom')\n")
    (tmp_path / "b_bad_ctor.py").write_text(
        GOOD.replace("good_plugin", "bad_ctor").replace(
            "    async def fetch",
            "    def __init__(self):\n        raise KeyError('x')\n\n    async def fetch",
        )
    )
    (tmp_path / "c_good.py").write_text(GOOD)
    registry = TrackerRegistry()
    assert registry.load_from_directory(tmp_path) == 1
    assert registry.get_by_name("good_plugin") is not None


def test_image_plugin_dir_not_writable_by_bot() -> None:
    dockerfile = (Path(__file__).resolve().parents[2] / "Dockerfile").read_text()
    assert not re.search(r"chown\s+-R\s+botuser:botuser\s+/app\b(?!/data)", dockerfile)
    assert "chown botuser:botuser /app/data" in dockerfile
