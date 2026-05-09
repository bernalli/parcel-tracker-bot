"""Built-in trackers registry."""

from __future__ import annotations

from parcel_tracker.config import Config
from parcel_tracker.core.registry import TrackerRegistry
from parcel_tracker.trackers.brt import BrtTracker
from parcel_tracker.trackers.dhl import DhlTracker
from parcel_tracker.trackers.gls_italy import GlsItalyTracker
from parcel_tracker.trackers.poste_italiane import PosteItalianeTracker
from parcel_tracker.trackers.sda import SdaTracker
from parcel_tracker.trackers.track17 import Track17Tracker


def register_builtins(registry: TrackerRegistry, config: Config) -> None:
    """Register all built-in trackers into the registry."""
    registry.register(BrtTracker())
    registry.register(GlsItalyTracker())
    registry.register(SdaTracker())
    registry.register(PosteItalianeTracker())
    registry.register(DhlTracker())

    if config.track17_api_key:
        registry.register(Track17Tracker(api_key=config.track17_api_key))


__all__ = ["register_builtins"]
