"""CSV export/import round trip and the forgiving parser."""

from __future__ import annotations

import csv
import io
from datetime import UTC, datetime

import pytest

from parcel_tracker.core.csv_io import (
    EXPORT_COLUMNS,
    MAX_IMPORT_BYTES,
    MAX_IMPORT_ROWS,
    CsvImportError,
    export_csv,
    import_csv,
    parse_csv,
)
from parcel_tracker.db.migrations import init_schema
from parcel_tracker.db.models import Parcel, ShipmentStatus
from parcel_tracker.db.repository import ParcelRepository


def test_export_has_header_and_values() -> None:
    parcel = Parcel(
        tracking_number="RR123456785IT",
        user_id=1,
        name="Mug, blue",
        order_ref="#1",
        tags=["vip", "gift"],
        status=ShipmentStatus.DELIVERED,
        carrier_name="Poste Italiane",
        created_at=datetime(2026, 1, 1, tzinfo=UTC),
        delivered_at=datetime(2026, 1, 4, tzinfo=UTC),
    )
    rows = list(csv.reader(io.StringIO(export_csv([parcel]))))
    assert tuple(rows[0]) == EXPORT_COLUMNS
    record = dict(zip(rows[0], rows[1], strict=True))
    assert record["name"] == "Mug, blue"
    assert record["tags"] == "vip, gift"
    assert record["status"] == "Delivered"
    assert record["carrier"] == "Poste Italiane"
    assert record["active"] == "yes"


def test_parse_semicolon_italian_header_with_bom() -> None:
    data = "﻿Codice;Ordine;Cliente;Destinazione;Note;Tag\nrr 123456785 it;#5;Ada;Roma;fragile;vip, express\n"
    parsed = parse_csv(data.encode("utf-8"))
    assert parsed.errors == []
    ((line, row),) = parsed.rows
    assert line == 2
    assert row.tracking_number == "RR123456785IT"
    assert (row.order_ref, row.recipient, row.destination, row.notes) == (
        "#5",
        "Ada",
        "Roma",
        "fragile",
    )
    assert row.tags == ["vip", "express"]


def test_parse_headerless_list_and_errors() -> None:
    data = b"RR123456785IT,Mug\n??\nRR123456785IT\n\nLX987654321CN\n"
    parsed = parse_csv(data)
    assert [r.tracking_number for _l, r in parsed.rows] == ["RR123456785IT", "LX987654321CN"]
    assert parsed.rows[0][1].name == "Mug"
    assert parsed.errors == [(2, "invalid tracking number"), (3, "duplicate in file")]


def test_parse_cp1252_and_empty() -> None:
    parsed = parse_csv("tracking,recipient\nRR123456785IT,Jos\xe9\n".encode("cp1252"))
    assert parsed.rows[0][1].recipient == "José"
    assert parse_csv(b"").rows == []


def test_parse_limits() -> None:
    with pytest.raises(CsvImportError):
        parse_csv(b"x" * (MAX_IMPORT_BYTES + 1))
    many = "\n".join(f"ZZ{i:08d}" for i in range(MAX_IMPORT_ROWS + 5)).encode()
    parsed = parse_csv(many)
    assert parsed.truncated
    assert len(parsed.rows) == MAX_IMPORT_ROWS


async def test_import_report(tmp_db_path) -> None:
    await init_schema(str(tmp_db_path))
    repo = ParcelRepository(str(tmp_db_path))
    await repo.create(Parcel(tracking_number="LX987654321CN", user_id=1))
    data = b"tracking_number,name\nRR123456785IT,Mug\nLX987654321CN,dup\n??,bad\nZZ12345678,over\n"
    report = await import_csv(repo, user_id=1, data=data, max_active=2)
    assert report.added == 1
    assert report.duplicates == 1
    assert report.invalid == 1
    assert report.over_limit == 1
    assert (5, "active shipment limit reached") in report.errors
    stored = await repo.get_for_user("RR123456785IT", user_id=1)
    assert stored is not None
    assert stored.name == "Mug"
