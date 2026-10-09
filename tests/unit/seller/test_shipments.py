"""Normalisation, validation, metadata limits and status grouping."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest

from parcel_tracker.core.shipments import (
    FIELD_LIMITS,
    MAX_TAGS,
    AddOutcome,
    ShipmentInput,
    StatusGroup,
    add_shipment,
    clean_tags,
    clip_field,
    extract_code_and_name,
    is_stalled,
    is_valid_tracking_number,
    looks_like_tracking,
    needs_attention,
    normalize_tracking_number,
    parse_bulk_codes,
    progress_index,
    status_group,
)
from parcel_tracker.db.migrations import init_schema
from parcel_tracker.db.models import Parcel, ShipmentStatus
from parcel_tracker.db.repository import ParcelRepository

NOW = datetime(2026, 10, 9, 12, 0, tzinfo=UTC)


class _Detector:
    def __init__(self, *priorities: int) -> None:
        self._matches = [SimpleNamespace(priority=p) for p in priorities]

    def detect(self, _code: str) -> list[SimpleNamespace]:
        return self._matches


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("1z 999 aa1-0123 4567 84", "1Z999AA10123456784"),
        ("  rr123456785it ", "RR123456785IT"),
        ("ABC.123_456", "ABC123456"),
        ("JD–014600006281", "JD014600006281"),
    ],
)
def test_normalize(raw: str, expected: str) -> None:
    assert normalize_tracking_number(raw) == expected


@pytest.mark.parametrize(
    ("code", "ok"),
    [("ABCDE", True), ("ABCD", False), ("A" * 40, True), ("A" * 41, False), ("AB/CD1", False)],
)
def test_is_valid(code: str, ok: bool) -> None:
    assert is_valid_tracking_number(code) is ok


def test_looks_like_tracking() -> None:
    assert looks_like_tracking("RR123456785IT")
    assert not looks_like_tracking("HELLOWORLD")
    assert not looks_like_tracking("AB12")
    # A carrier-specific pattern wins over the digit heuristic…
    assert looks_like_tracking("ABCDEFGH", _Detector(50))
    # …but the catch-all fallback (priority 1) does not.
    assert not looks_like_tracking("ABCDEFGH", _Detector(1))


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("1Z 999 AA1 0123 4567 84", ("1Z999AA10123456784", None)),
        ("9400 1000 0000 0000 0000 00", ("9400100000000000000000", None)),
        ("RR123456785IT gift for mom", ("RR123456785IT", "gift for mom")),
        ("Order 12345678 shipped", ("ORDER", "12345678 shipped")),
        ("my new phone 2024", ("MY", "new phone 2024")),
    ],
)
def test_extract_code_and_name(text: str, expected: tuple[str, str | None]) -> None:
    assert extract_code_and_name(text, None) == expected


def test_parse_bulk_codes() -> None:
    text = "RR123456785IT mom\n\nLX987654321CN\nRR123456785IT again\nnot a code"
    assert parse_bulk_codes(text, None) == [("RR123456785IT", "mom"), ("LX987654321CN", None)]
    assert parse_bulk_codes("RR123456785IT\nsecond line note", None) == []
    assert parse_bulk_codes("RR123456785IT", None) == []


def test_clip_and_tags() -> None:
    assert clip_field("name", "  a   b ") == "a b"
    assert clip_field("name", "   ") is None
    assert clip_field("name", None) is None
    assert len(clip_field("recipient", "x" * 500) or "") == FIELD_LIMITS["recipient"]
    assert clip_field("notes", " line1\nline2 ") == "line1\nline2"
    assert clean_tags("VIP, express #Gift;vip") == ["vip", "express", "gift"]
    assert clean_tags(["A", " a ", "b"]) == ["a", "b"]
    assert clean_tags(None) == []
    assert len(clean_tags(",".join(f"t{i}" for i in range(30)))) == MAX_TAGS


async def test_add_shipment_outcomes(tmp_db_path) -> None:
    await init_schema(str(tmp_db_path))
    repo = ParcelRepository(str(tmp_db_path))
    outcome, parcel = await add_shipment(
        repo,
        user_id=1,
        data=ShipmentInput("rr 123456785 it", order_ref="  #9 ", tags=["X"]),
        max_active=2,
    )
    assert outcome is AddOutcome.ADDED
    assert parcel is not None
    assert parcel.tracking_number == "RR123456785IT"
    assert parcel.order_ref == "#9"
    assert parcel.tags == ["x"]
    dup, _ = await add_shipment(repo, user_id=1, data=ShipmentInput("RR123456785IT"), max_active=2)
    assert dup is AddOutcome.DUPLICATE
    bad, _ = await add_shipment(repo, user_id=1, data=ShipmentInput("??"), max_active=2)
    assert bad is AddOutcome.INVALID
    await add_shipment(repo, user_id=1, data=ShipmentInput("LX987654321CN"), max_active=2)
    full, _ = await add_shipment(repo, user_id=1, data=ShipmentInput("ZZ12345678"), max_active=2)
    assert full is AddOutcome.LIMIT
    unlimited, _ = await add_shipment(
        repo, user_id=1, data=ShipmentInput("ZZ12345678"), max_active=0
    )
    assert unlimited is AddOutcome.ADDED


def _parcel(status: ShipmentStatus, *, days_quiet: float, active: bool = True) -> Parcel:
    return Parcel(
        tracking_number="X1234567",
        user_id=1,
        status=status,
        is_active=active,
        last_change_at=NOW - timedelta(days=days_quiet),
    )


def test_stalled_and_attention() -> None:
    quiet = _parcel(ShipmentStatus.IN_TRANSIT, days_quiet=6)
    assert is_stalled(quiet, NOW, 5)
    assert needs_attention(quiet, NOW, 5)
    assert not is_stalled(quiet, NOW, 0)
    assert not is_stalled(_parcel(ShipmentStatus.IN_TRANSIT, days_quiet=2), NOW, 5)
    assert not is_stalled(_parcel(ShipmentStatus.DELIVERED, days_quiet=30), NOW, 5)
    assert not is_stalled(_parcel(ShipmentStatus.IN_TRANSIT, days_quiet=9, active=False), NOW, 5)
    assert needs_attention(_parcel(ShipmentStatus.EXCEPTION, days_quiet=0), NOW, 5)
    assert not needs_attention(
        _parcel(ShipmentStatus.EXCEPTION, days_quiet=0, active=False), NOW, 5
    )
    no_clock = Parcel(tracking_number="X", user_id=1, status=ShipmentStatus.IN_TRANSIT)
    assert not is_stalled(no_clock, NOW, 5)


def test_groups_cover_every_status() -> None:
    for status in ShipmentStatus:
        assert isinstance(status_group(status), StatusGroup)
        assert -1 <= progress_index(status) <= 4
    assert status_group(ShipmentStatus.CUSTOMS) is StatusGroup.TRANSIT
    assert progress_index(ShipmentStatus.DELIVERED) == 4
