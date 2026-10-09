"""Picking tracking codes out of what sellers actually paste."""

from __future__ import annotations

from collections.abc import Iterator
from types import SimpleNamespace

import pytest

from parcel_tracker.core.detector import CourierDetector
from parcel_tracker.core.registry import TrackerRegistry
from parcel_tracker.core.shipments import (
    extract_code_and_name,
    find_code_in_text,
    parse_bulk_codes,
    pick_single_code,
    strip_list_marker,
)
from parcel_tracker.trackers import register_builtins


@pytest.fixture(scope="module")
def detector() -> Iterator[CourierDetector]:
    registry = TrackerRegistry()
    register_builtins(
        registry, SimpleNamespace(track17_api_key="k", dhl_api_key="k", request_timeout=30)
    )
    yield CourierDetector(registry)


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("RR 123 456 785 IT Scarf", ("RR123456785IT", "Scarf")),
        ("JJD 0000 1234 5678 9012 blue mug", ("JJD0000123456789012", "blue mug")),
        ("1Z 999 AA1 0123 4567 84", ("1Z999AA10123456784", None)),
        ("LX987654321CN — desk lamp", ("LX987654321CN", "desk lamp")),
        ("RR123456785IT: order 1042", ("RR123456785IT", "order 1042")),
        ("1Z999AA10123456784 scarpe blu", ("1Z999AA10123456784", "scarpe blu")),
        ("Order 12345678 shipped", ("ORDER", "12345678 shipped")),
        ("", ("", None)),
    ],
)
def test_extract_code_and_name(
    detector: CourierDetector, text: str, expected: tuple[str, str | None]
) -> None:
    assert extract_code_and_name(text, detector) == expected


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("Tracking: RR123456785IT", "RR123456785IT"),
        ("Il mio pacco RR123456785IT è fermo", "RR123456785IT"),
        (
            "https://www.dhl.com/it-it/home/tracking.html?tracking-id=JJD0000123456789012",
            "JJD0000123456789012",
        ),
        ("tracking:rr123456785it", "RR123456785IT"),
        # A bare number in a sentence is more likely a phone or an order number.
        ("Call me at 3331234567", None),
        # Two different codes: ambiguous, so none is picked.
        ("RR123456785IT or LX987654321CN?", None),
        ("Ciao, come stai?", None),
    ],
)
def test_find_code_in_text(detector: CourierDetector, text: str, expected: str | None) -> None:
    assert find_code_in_text(text, detector) == expected


def test_pick_single_code(detector: CourierDetector) -> None:
    assert pick_single_code("RR123456785IT gift", detector) == ("RR123456785IT", "gift")
    assert pick_single_code("Tracking: RR123456785IT", detector) == ("RR123456785IT", None)
    assert pick_single_code("hello there", detector) is None


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        (
            "1. RR123456785IT mug\n2. LX987654321CN",
            [("RR123456785IT", "mug"), ("LX987654321CN", None)],
        ),
        (
            "- RR123456785IT\n• LX987654321CN lamp",
            [("RR123456785IT", None), ("LX987654321CN", "lamp")],
        ),
        (
            "RR123456785IT, LX987654321CN; CP123456789DE",
            [("RR123456785IT", None), ("LX987654321CN", None), ("CP123456789DE", None)],
        ),
        ("RR123456785IT LX987654321CN", [("RR123456785IT", None), ("LX987654321CN", None)]),
        # One line with a name that merely contains digits is a single parcel.
        ("RR123456785IT gift 2024", []),
        ("RR123456785IT, RR123456785IT", []),
    ],
)
def test_parse_bulk_codes(
    detector: CourierDetector, text: str, expected: list[tuple[str, str | None]]
) -> None:
    assert parse_bulk_codes(text, detector) == expected


@pytest.mark.parametrize(
    ("line", "expected"),
    [
        ("1. RR123456785IT", "RR123456785IT"),
        ("12) RR123456785IT mug", "RR123456785IT mug"),
        ("* RR123456785IT", "RR123456785IT"),
        ("  RR123456785IT  ", "RR123456785IT"),
        ("2024 sales", "2024 sales"),
    ],
)
def test_strip_list_marker(line: str, expected: str) -> None:
    assert strip_list_marker(line) == expected
