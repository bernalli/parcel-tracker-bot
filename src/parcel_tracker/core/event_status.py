"""Best-effort mapping from a free-text event description to a ShipmentStatus.

Some trackers — notably the Italian scraper plugins (BRT/GLS Italy/SDA) — return
``found=True`` with a populated event history but leave ``TrackingResult.status``
at its ``NOT_FOUND`` default. The scheduler uses :func:`status_from_text` as a
defensive fallback so those parcels still show a meaningful status (and trigger
notifications / the delivered transition) like the API-backed trackers do.

The keyword set mirrors the per-tracker heuristics already used by the built-in
scrapers (see ``trackers/bpost.py``) and adds the Italian carrier vocabulary.
"""

from __future__ import annotations

from parcel_tracker.db.models import ShipmentStatus

# Checked top-to-bottom; first keyword hit wins. Order matters: terminal and
# more specific states are listed before broader ones (e.g. DELIVERED before
# OUT_FOR_DELIVERY so "consegnato" is not shadowed by "in consegna").
_STATUS_KEYWORDS: tuple[tuple[ShipmentStatus, tuple[str, ...]], ...] = (
    (ShipmentStatus.DELIVERED, ("delivered", "consegnat", "consegna effettuata")),
    (
        ShipmentStatus.OUT_FOR_DELIVERY,
        ("out for delivery", "in consegna", "in distribuzione", "in delivery"),
    ),
    (
        ShipmentStatus.RETURNED,
        (
            "returned",
            "return to sender",
            "reso al mittente",
            "in restituzione",
            "ritorno al mittente",
        ),
    ),
    # CUSTOMS before UNDELIVERED: a customs hold may also mention a future
    # "delivery attempt", which must not shadow the customs classification.
    (ShipmentStatus.CUSTOMS, ("customs", "dogana", "sdoganamento")),
    (
        ShipmentStatus.UNDELIVERED,
        (
            "undelivered",
            "delivery failed",
            "failed delivery",
            "delivery unsuccessful",
            "unable to deliver",
            "could not be delivered",
            "delivery attempt",
            "attempted delivery",
            "mancata consegna",
            "consegna non riuscita",
            "tentativo di consegna",
            "tentata consegna",
            "destinatario assente",
        ),
    ),
    (ShipmentStatus.EXCEPTION, ("exception", "anomalia", "giacenza", "fermo deposito")),
    (ShipmentStatus.ALERT, ("alert", "allerta")),
    (
        ShipmentStatus.PICKUP,
        (
            "picked up",
            "pickup",
            "collected",
            "presa in carico",
            "preso in carico",
            "ritirato",
            "ritiro",
        ),
    ),
    (
        ShipmentStatus.INFO_RECEIVED,
        (
            "info received",
            "shipment information",
            "spedizione creata",
            "etichetta creata",
            "registrata",
        ),
    ),
)


def status_from_text(text: str | None) -> ShipmentStatus | None:
    """Infer a shipment status from an event description.

    Returns the matched status; ``IN_TRANSIT`` when the text is non-empty but
    matches no keyword (a parcel with a real movement event is at least in
    transit); and ``None`` when there is no text to interpret (so callers keep
    whatever status they already had).
    """
    if text is None:
        return None
    low = text.strip().casefold()
    if not low:
        return None
    for status, keywords in _STATUS_KEYWORDS:
        if any(keyword in low for keyword in keywords):
            return status
    return ShipmentStatus.IN_TRANSIT
