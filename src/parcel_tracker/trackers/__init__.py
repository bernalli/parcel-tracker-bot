"""Built-in trackers registry (international only — no national IT trackers)."""

from __future__ import annotations

from parcel_tracker.config import Config
from parcel_tracker.core.http_client import HttpClient
from parcel_tracker.core.registry import TrackerRegistry
from parcel_tracker.trackers.amazon_logistics import AmazonLogisticsTracker
from parcel_tracker.trackers.aramex import AramexTracker
from parcel_tracker.trackers.australia_post import AustraliaPostTracker
from parcel_tracker.trackers.bpost import BpostTracker
from parcel_tracker.trackers.canada_post import CanadaPostTracker
from parcel_tracker.trackers.china_post import ChinaPostTracker
from parcel_tracker.trackers.correios import CorreiosTracker
from parcel_tracker.trackers.correos import CorreosTracker
from parcel_tracker.trackers.deutsche_post import DeutschePostTracker
from parcel_tracker.trackers.dhl import DhlTracker
from parcel_tracker.trackers.dhl_api import DhlApiTracker
from parcel_tracker.trackers.dpd import DpdTracker
from parcel_tracker.trackers.ems import EmsTracker
from parcel_tracker.trackers.evri import EvriTracker
from parcel_tracker.trackers.fedex import FedexTracker
from parcel_tracker.trackers.gls_europe import GlsEuropeTracker
from parcel_tracker.trackers.japan_post import JapanPostTracker
from parcel_tracker.trackers.la_poste import LaPosteTracker
from parcel_tracker.trackers.oesterreichische_post import OesterreichischePostTracker
from parcel_tracker.trackers.postnl import PostnlTracker
from parcel_tracker.trackers.royal_mail import RoyalMailTracker
from parcel_tracker.trackers.singapore_post import SingaporePostTracker
from parcel_tracker.trackers.swisspost import SwissPostTracker
from parcel_tracker.trackers.track17 import Track17Tracker
from parcel_tracker.trackers.ups import UpsTracker
from parcel_tracker.trackers.usps import UspsTracker
from parcel_tracker.trackers.yodel import YodelTracker

_SCRAPERS = (
    UpsTracker,
    UspsTracker,
    RoyalMailTracker,
    LaPosteTracker,
    DeutschePostTracker,
    AramexTracker,
    AustraliaPostTracker,
    BpostTracker,
    CanadaPostTracker,
    CorreiosTracker,
    CorreosTracker,
    DhlTracker,
    DpdTracker,
    EvriTracker,
    FedexTracker,
    GlsEuropeTracker,
    OesterreichischePostTracker,
    PostnlTracker,
    SwissPostTracker,
    YodelTracker,
)
_TRACK17_BACKED = (
    AmazonLogisticsTracker,
    ChinaPostTracker,
    EmsTracker,
    SingaporePostTracker,
    JapanPostTracker,
)


def register_builtins(registry: TrackerRegistry, config: Config) -> HttpClient:
    """Register all built-in trackers and return the HTTP client they share.

    One client means one connection pool and one ``REQUEST_TIMEOUT`` for every
    carrier; the caller closes it on shutdown.
    """
    client = HttpClient(timeout=float(config.request_timeout))
    for scraper in _SCRAPERS:
        registry.register(scraper(http_client=client))

    if config.dhl_api_key:
        registry.register(DhlApiTracker(api_key=config.dhl_api_key, http_client=client))

    track17_instance: Track17Tracker | None = None
    if config.track17_api_key:
        track17_instance = Track17Tracker(api_key=config.track17_api_key, http_client=client)
        registry.register(track17_instance)

    # Detection-only trackers that delegate to 17track; without a key they report
    # "track17 not configured" and the parcel is not tracked.
    for backed in _TRACK17_BACKED:
        registry.register(backed(track17=track17_instance))
    return client


__all__ = ["register_builtins"]
