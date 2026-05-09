"""Built-in trackers registry (international only — no national IT trackers)."""

from __future__ import annotations

from parcel_tracker.config import Config
from parcel_tracker.core.registry import TrackerRegistry
from parcel_tracker.trackers.dhl import DhlTracker
from parcel_tracker.trackers.royal_mail import RoyalMailTracker
from parcel_tracker.trackers.track17 import Track17Tracker
from parcel_tracker.trackers.ups import UpsTracker
from parcel_tracker.trackers.usps import UspsTracker


def register_builtins(registry: TrackerRegistry, config: Config) -> None:
    """Register all built-in trackers into the registry."""
    registry.register(UpsTracker())
    registry.register(UspsTracker())
    registry.register(RoyalMailTracker())
    registry.register(DhlTracker())
    if config.track17_api_key:
        registry.register(Track17Tracker(api_key=config.track17_api_key))


__all__ = ["register_builtins"]
