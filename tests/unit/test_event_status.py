"""Tests for the event-text → ShipmentStatus fallback mapper.

This helper exists because the Italian scraper plugins (BRT/GLS Italy/SDA)
return ``found=True`` with events but leave ``status`` at the NOT_FOUND default;
the scheduler uses it to recover a sensible status from the latest event text.
"""

from __future__ import annotations

import pytest

from parcel_tracker.core.event_status import status_from_text
from parcel_tracker.db.models import ShipmentStatus


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        # BRT English event labels — the live-bug case (vas.brt.it returns English)
        ("ARRIVED AT DEPOT", ShipmentStatus.IN_TRANSIT),
        ("DEPARTED", ShipmentStatus.IN_TRANSIT),
        ("COLLECTED", ShipmentStatus.PICKUP),
        ("DELIVERED", ShipmentStatus.DELIVERED),
        ("OUT FOR DELIVERY", ShipmentStatus.OUT_FOR_DELIVERY),
        # Italian carrier vocabulary (BRT/GLS Italy/SDA/Poste)
        ("Consegnato al destinatario", ShipmentStatus.DELIVERED),
        ("In consegna", ShipmentStatus.OUT_FOR_DELIVERY),
        ("Presa in carico", ShipmentStatus.PICKUP),
        ("In transito", ShipmentStatus.IN_TRANSIT),
        ("Spedizione in giacenza", ShipmentStatus.EXCEPTION),
        # any non-empty unknown event still means the parcel is moving
        ("Some unrecognised carrier note", ShipmentStatus.IN_TRANSIT),
    ],
)
def test_status_from_text_maps_known_events(text: str, expected: ShipmentStatus) -> None:
    assert status_from_text(text) is expected


def test_status_from_text_returns_none_for_empty() -> None:
    assert status_from_text("") is None
    assert status_from_text(None) is None
    assert status_from_text("   ") is None


@pytest.mark.parametrize(
    "text",
    [
        "Non consegnato - destinatario assente",
        "NON CONSEGNATO",
        "Non è stato consegnato",
        "Spedizione non ancora consegnata",
        "Not delivered",
        "Not yet delivered",
        "Undelivered",
        "Parcel could not be delivered",
        "Package cannot be delivered",
        "Shipment wasn't delivered",
    ],
)
def test_status_from_text_negated_delivery_is_undelivered(text: str) -> None:
    """A negated delivery contains the DELIVERED keywords and must not resolve to it (#16)."""
    assert status_from_text(text) is ShipmentStatus.UNDELIVERED


@pytest.mark.parametrize(
    "text",
    ["Delivered", "Consegnato", "Consegnata al destinatario", "Delivered to the neighbour"],
)
def test_status_from_text_positive_delivery_unchanged(text: str) -> None:
    assert status_from_text(text) is ShipmentStatus.DELIVERED
