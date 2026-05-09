"""Courier auto-detector — match tracking ID or URL against registered trackers."""

from __future__ import annotations

from parcel_tracker.core.registry import TrackerRegistry
from parcel_tracker.core.tracker_base import AbstractTracker


class CourierDetector:
    """
    Match a tracking ID or URL against all registered trackers.

    Returns matches sorted by descending priority (highest first).
    """

    def __init__(self, registry: TrackerRegistry) -> None:
        self._registry = registry

    def detect(self, tracking_id_or_url: str) -> list[AbstractTracker]:
        matches = [
            tracker for tracker in self._registry.iter_all() if tracker.detect(tracking_id_or_url)
        ]
        matches.sort(key=lambda t: t.priority, reverse=True)
        return matches
