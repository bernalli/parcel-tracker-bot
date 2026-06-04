"""Heuristic transport-mode inference from carrier name + event description."""

from __future__ import annotations

# Ordered: first matching mode wins.
_KEYWORDS: list[tuple[str, tuple[str, ...]]] = [
    ("plane", ("flight", "airport", "air ", "by air", "aircraft", "aereo", "volo")),
    ("ship", ("vessel", "port of", "seaport", "by sea", "nave", "porto", "maritime")),
    ("train", ("rail", "train", "treno", "ferroviar")),
    ("truck", ("out for delivery", "courier", "van", "truck", "road", "in consegna",
               "camion", "su strada", "delivery vehicle")),
]


def infer_transport_mode(carrier: str | None, description: str | None) -> str:
    """Return one of: plane, ship, train, truck, parcel (default)."""
    haystack = f"{carrier or ''} {description or ''}".lower()
    for mode, words in _KEYWORDS:
        if any(w in haystack for w in words):
            return mode
    return "parcel"
