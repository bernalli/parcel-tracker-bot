"""Tracker plugin registry: built-in + drop-in directory + entry-points discovery."""

from __future__ import annotations

import importlib.util
import logging
from collections.abc import Iterator
from pathlib import Path

from parcel_tracker.core.tracker_base import AbstractTracker

logger = logging.getLogger(__name__)


class TrackerRegistry:
    """
    Registry of tracker instances by name.

    Two ways to register:
    1. `register(tracker)` — explicit (used by built-in trackers at startup).
    2. `load_from_directory(path)` — scan a directory for `.py` files,
       import each, and register the `Tracker` class found inside.
    """

    def __init__(self) -> None:
        self._trackers: dict[str, AbstractTracker] = {}

    def register(self, tracker: AbstractTracker) -> None:
        if tracker.name in self._trackers:
            raise ValueError(f"Tracker '{tracker.name}' already registered")
        self._trackers[tracker.name] = tracker
        logger.debug("Registered tracker: %s (priority=%d)", tracker.name, tracker.priority)

    def get_by_name(self, name: str) -> AbstractTracker | None:
        return self._trackers.get(name)

    def iter_all(self) -> Iterator[AbstractTracker]:
        yield from self._trackers.values()

    def load_from_directory(self, directory: Path) -> int:
        """Scan a directory for plugin .py files and register each Tracker class."""
        if not directory.exists() or not directory.is_dir():
            return 0

        loaded = 0
        for py_file in sorted(directory.glob("*.py")):
            if py_file.name.startswith("_"):
                continue

            module_name = f"_parcel_plugin_{py_file.stem}"
            spec = importlib.util.spec_from_file_location(module_name, py_file)
            if spec is None or spec.loader is None:
                logger.warning("Could not load plugin file: %s", py_file)
                continue

            module = importlib.util.module_from_spec(spec)
            try:
                spec.loader.exec_module(module)
            except (ImportError, SyntaxError) as exc:
                logger.error("Failed to import plugin %s: %s", py_file, exc)
                continue

            tracker_cls = getattr(module, "Tracker", None)
            if tracker_cls is None or not isinstance(tracker_cls, type):
                logger.warning("Plugin %s has no `Tracker` class; skipping", py_file)
                continue
            if not issubclass(tracker_cls, AbstractTracker):
                logger.warning(
                    "Plugin %s `Tracker` class is not AbstractTracker subclass; skipping",
                    py_file,
                )
                continue

            try:
                self.register(tracker_cls())
                loaded += 1
            except ValueError as exc:
                logger.warning("Skipping duplicate plugin %s: %s", py_file, exc)

        logger.info("Loaded %d plugins from %s", loaded, directory)
        return loaded
