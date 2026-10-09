"""CSV export and import of shipments.

Import is forgiving on purpose, because the file usually comes out of a shop
back-office or a spreadsheet: comma, semicolon or tab delimiters, an optional
UTF-8 BOM, header names in several languages, or a bare list of codes with no
header at all.
"""

from __future__ import annotations

import csv
import io
from collections.abc import Iterable
from dataclasses import dataclass, field

from parcel_tracker.core.shipments import (
    AddOutcome,
    ShipmentInput,
    ShipmentRepo,
    add_shipment,
    clean_tags,
    is_valid_tracking_number,
    normalize_tracking_number,
)
from parcel_tracker.db.models import Parcel

MAX_IMPORT_ROWS = 2000
MAX_IMPORT_BYTES = 1_000_000

EXPORT_COLUMNS: tuple[str, ...] = (
    "tracking_number",
    "name",
    "order_ref",
    "recipient",
    "destination",
    "tags",
    "notes",
    "carrier",
    "status",
    "last_event",
    "last_location",
    "last_event_time",
    "added_at",
    "delivered_at",
    "active",
)

# Accepted header names (lower-cased, spaces/underscores/dashes removed) per field.
_ALIASES: dict[str, tuple[str, ...]] = {
    "tracking_number": (
        "trackingnumber",
        "tracking",
        "trackingcode",
        "trackingno",
        "trackingid",
        "code",
        "awb",
        "codice",
        "codicetracking",
        "numerotracking",
        "numerospedizione",
        "seguimiento",
        "numerodeseguimiento",
        "numerodesuivi",
        "suivi",
        "sendungsnummer",
        "sendungsverfolgung",
    ),
    "name": ("name", "nome", "nombre", "nom", "description", "descrizione", "item", "product"),
    "order_ref": (
        "orderref",
        "order",
        "ordernumber",
        "orderid",
        "ordine",
        "numeroordine",
        "pedido",
        "commande",
        "bestellung",
        "bestellnummer",
        "reference",
        "riferimento",
    ),
    "recipient": (
        "recipient",
        "customer",
        "customername",
        "cliente",
        "destinatario",
        "client",
        "destinataire",
        "empfanger",
        "empfaenger",
        "kunde",
    ),
    "destination": (
        "destination",
        "destinazione",
        "destino",
        "city",
        "citta",
        "country",
        "paese",
        "pais",
        "pays",
        "ort",
        "land",
        "shippingaddress",
        "address",
        "indirizzo",
    ),
    "notes": ("notes", "note", "notas", "notiz", "notizen", "comment", "comments", "commento"),
    "tags": ("tags", "tag", "etichette", "labels", "etiquetas"),
}
_LOOKUP = {alias: key for key, aliases in _ALIASES.items() for alias in aliases}


def _norm_header(value: str) -> str:
    return "".join(ch for ch in value.lower() if ch.isalnum())


def export_csv(parcels: Iterable[Parcel]) -> str:
    """Render shipments as CSV text (UTF-8, comma-separated, header row)."""
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(EXPORT_COLUMNS)
    for p in parcels:
        writer.writerow(
            [
                p.tracking_number,
                p.name or "",
                p.order_ref or "",
                p.recipient or "",
                p.destination or "",
                ", ".join(p.tags),
                p.notes or "",
                p.carrier_name or p.carrier_code or "",
                p.status.value,
                p.last_event or "",
                p.last_location or "",
                p.last_event_time or "",
                p.created_at.isoformat() if p.created_at else "",
                p.delivered_at.isoformat() if p.delivered_at else "",
                "yes" if p.is_active else "no",
            ]
        )
    return buf.getvalue()


@dataclass(slots=True)
class ParsedCsv:
    rows: list[tuple[int, ShipmentInput]] = field(default_factory=list)
    errors: list[tuple[int, str]] = field(default_factory=list)
    truncated: bool = False


class CsvImportError(ValueError):
    """The file cannot be read as CSV at all (encoding, size, no usable column)."""


def _decode(data: bytes) -> str:
    if len(data) > MAX_IMPORT_BYTES:
        raise CsvImportError("file too large")
    for encoding in ("utf-8-sig", "cp1252"):
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    raise CsvImportError("unsupported encoding")  # pragma: no cover — cp1252 decodes all bytes


def _dialect(text: str) -> type[csv.Dialect] | csv.Dialect:
    sample = text[:4096]
    try:
        return csv.Sniffer().sniff(sample, delimiters=",;\t|")
    except csv.Error:
        return csv.excel


def parse_csv(data: bytes) -> ParsedCsv:
    """Parse an uploaded CSV into shipment inputs plus per-line errors."""
    text = _decode(data)
    reader = csv.reader(io.StringIO(text), _dialect(text))
    rows = list(reader)
    result = ParsedCsv()
    if not rows:
        return result
    header = [_LOOKUP.get(_norm_header(cell)) for cell in rows[0]]
    if "tracking_number" in header:
        columns = header
        body = list(enumerate(rows[1:], start=2))
    else:
        # No recognisable header: the first column holds the codes.
        columns = ["tracking_number", "name", *([None] * max(0, len(rows[0]) - 2))]
        body = list(enumerate(rows, start=1))
    if len(body) > MAX_IMPORT_ROWS:
        body = body[:MAX_IMPORT_ROWS]
        result.truncated = True
    seen: set[str] = set()
    for line_no, cells in body:
        if not any(c.strip() for c in cells):
            continue
        row, error = _row_input(columns, cells, seen)
        if error is not None:
            result.errors.append((line_no, error))
        elif row is not None:
            result.rows.append((line_no, row))
    return result


def _row_input(
    columns: list[str | None], cells: list[str], seen: set[str]
) -> tuple[ShipmentInput | None, str | None]:
    values: dict[str, str] = {}
    for key, cell in zip(columns, cells, strict=False):
        if key and cell.strip() and key not in values:
            values[key] = cell.strip()
    code = normalize_tracking_number(values.get("tracking_number", ""))
    if not is_valid_tracking_number(code):
        return None, "invalid tracking number"
    if code in seen:
        return None, "duplicate in file"
    seen.add(code)
    return (
        ShipmentInput(
            tracking_number=code,
            name=values.get("name"),
            order_ref=values.get("order_ref"),
            recipient=values.get("recipient"),
            destination=values.get("destination"),
            notes=values.get("notes"),
            tags=clean_tags(values.get("tags")),
        ),
        None,
    )


@dataclass(slots=True)
class ImportReport:
    added: int = 0
    duplicates: int = 0
    invalid: int = 0
    over_limit: int = 0
    truncated: bool = False
    errors: list[tuple[int, str]] = field(default_factory=list)


async def import_csv(
    repo: ShipmentRepo, *, user_id: int, data: bytes, max_active: int
) -> ImportReport:
    """Parse and store every row; raises CsvImportError for unreadable files."""
    parsed = parse_csv(data)
    report = ImportReport(invalid=len(parsed.errors), truncated=parsed.truncated)
    report.errors.extend(parsed.errors)
    for line_no, row in parsed.rows:
        outcome, _parcel = await add_shipment(
            repo, user_id=user_id, data=row, max_active=max_active
        )
        if outcome is AddOutcome.ADDED:
            report.added += 1
        elif outcome is AddOutcome.DUPLICATE:
            report.duplicates += 1
        elif outcome is AddOutcome.LIMIT:
            report.over_limit += 1
            report.errors.append((line_no, "active shipment limit reached"))
        else:
            report.invalid += 1
            report.errors.append((line_no, "invalid tracking number"))
    return report
