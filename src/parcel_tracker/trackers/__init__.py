"""Built-in trackers registry (international only — no national IT trackers)."""

from __future__ import annotations

from parcel_tracker.config import Config
from parcel_tracker.core.registry import TrackerRegistry
from parcel_tracker.trackers.aramex import AramexTracker
from parcel_tracker.trackers.australia_post import AustraliaPostTracker
from parcel_tracker.trackers.bpost import BpostTracker
from parcel_tracker.trackers.canada_post import CanadaPostTracker
from parcel_tracker.trackers.correios import CorreiosTracker
from parcel_tracker.trackers.correos import CorreosTracker
from parcel_tracker.trackers.deutsche_post import DeutschePostTracker
from parcel_tracker.trackers.dhl import DhlTracker
from parcel_tracker.trackers.dpd import DpdTracker
from parcel_tracker.trackers.evri import EvriTracker
from parcel_tracker.trackers.fedex import FedexTracker
from parcel_tracker.trackers.gls_europe import GlsEuropeTracker
from parcel_tracker.trackers.la_poste import LaPosteTracker
from parcel_tracker.trackers.oesterreichische_post import OesterreichischePostTracker
from parcel_tracker.trackers.postnl import PostnlTracker
from parcel_tracker.trackers.royal_mail import RoyalMailTracker
from parcel_tracker.trackers.swisspost import SwissPostTracker
from parcel_tracker.trackers.track17 import Track17Tracker
from parcel_tracker.trackers.ups import UpsTracker
from parcel_tracker.trackers.usps import UspsTracker
from parcel_tracker.trackers.yodel import YodelTracker


def register_builtins(registry: TrackerRegistry, config: Config) -> None:
    """Register all built-in trackers into the registry."""
    registry.register(UpsTracker())
    registry.register(UspsTracker())
    registry.register(RoyalMailTracker())
    registry.register(LaPosteTracker())
    registry.register(DeutschePostTracker())
    registry.register(AramexTracker())
    registry.register(AustraliaPostTracker())
    registry.register(BpostTracker())
    registry.register(CanadaPostTracker())
    registry.register(CorreiosTracker())
    registry.register(CorreosTracker())
    registry.register(DhlTracker())
    registry.register(DpdTracker())
    registry.register(EvriTracker())
    registry.register(FedexTracker())
    registry.register(GlsEuropeTracker())
    registry.register(OesterreichischePostTracker())
    registry.register(PostnlTracker())
    registry.register(SwissPostTracker())
    registry.register(YodelTracker())
    if config.track17_api_key:
        registry.register(Track17Tracker(api_key=config.track17_api_key))


__all__ = ["register_builtins"]
