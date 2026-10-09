"""Shipment rules shared by every entry point (Telegram, web dashboard, API, CSV).

Keeping normalisation, validation, field limits and status grouping here means a
code pasted in the bot, typed in the dashboard or imported from a spreadsheet is
treated exactly the same way.
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Protocol

from parcel_tracker.db.models import Parcel, ShipmentStatus

# Longest real-world codes are ~35 chars; 40 also keeps "parcel:<action>:<code>"
# inside Telegram's 64-byte callback_data limit.
CODE_MAX_LEN = 40
CODE_MIN_LEN = 5

# Raw-character caps for user-supplied metadata.
FIELD_LIMITS: dict[str, int] = {
    "name": 64,
    "order_ref": 64,
    "recipient": 100,
    "destination": 100,
    "notes": 1000,
}
# Free-text seller fields editable from the dashboard (tags are handled apart).
DETAIL_FIELDS_WEB: tuple[str, ...] = ("name", "order_ref", "recipient", "destination", "notes")
MAX_TAGS = 10
TAG_MAX_LEN = 24

_SEPARATORS = re.compile(r"[\s\-‐-―_.]+")
_CODE_RE = re.compile(rf"^[A-Z0-9]{{{CODE_MIN_LEN},{CODE_MAX_LEN}}}$")
# Heuristic for codes found in free text (no carrier pattern matched): long enough
# and with enough digits that ordinary words are not mistaken for codes.
_FREE_TEXT_SHAPE = re.compile(r"^[A-Z0-9]{8,35}$")
_FREE_TEXT_MIN_DIGITS = 3


class _DetectorLike(Protocol):
    def detect(self, tracking_id_or_url: str) -> Sequence[object]: ...


def normalize_tracking_number(raw: str) -> str:
    """Upper-case and drop the spaces, dashes and dots carriers print inside codes.

    ``"1z 999 aa1-0123 4567 84"`` → ``"1Z999AA10123456784"``. NFKC folds
    full-width characters (``"１Ｚ…"`` from some phone keyboards) to ASCII; any
    other non-ASCII character is left in place and fails validation.
    """
    folded = unicodedata.normalize("NFKC", raw)
    return _SEPARATORS.sub("", folded.strip()).upper()


# --- UPU S10 (international postal items: RR123456785IT, LX…CN, CP…DE) --------

_S10_RE = re.compile(r"^([A-Z]{2})(\d{8})(\d)([A-Z]{2})$")
_S10_WEIGHTS = (8, 6, 4, 2, 3, 5, 9, 7)
_S10_CHECK_TEN = 10
_S10_CHECK_ELEVEN = 11

# Postal operator for the S10 country suffix (the country that issued the item).
S10_OPERATORS: dict[str, str] = {
    "AT": "Österreichische Post",
    "AU": "Australia Post",
    "BE": "bpost",
    "BR": "Correios",
    "CA": "Canada Post",
    "CH": "Swiss Post",
    "CN": "China Post",
    "CZ": "Česká pošta",
    "DE": "Deutsche Post",
    "DK": "PostNord Denmark",
    "ES": "Correos",
    "FI": "Posti",
    "FR": "La Poste",
    "GB": "Royal Mail",
    "GR": "ELTA Hellenic Post",
    "HK": "Hongkong Post",
    "IE": "An Post",
    "IL": "Israel Post",
    "IN": "India Post",
    "IT": "Poste Italiane",
    "JP": "Japan Post",
    "KR": "Korea Post",
    "LU": "POST Luxembourg",
    "MX": "Correos de México",
    "MY": "Pos Malaysia",
    "NL": "PostNL",
    "NO": "Posten Norge",
    "NZ": "NZ Post",
    "PL": "Poczta Polska",
    "PT": "CTT",
    "RO": "Poșta Română",
    "RU": "Russian Post",
    "SE": "PostNord Sweden",
    "SG": "Singapore Post",
    "TH": "Thailand Post",
    "TR": "PTT",
    "TW": "Chunghwa Post",
    "UA": "Ukrposhta",
    "US": "USPS",
    "ZA": "South African Post Office",
}


def s10_check_digit(serial: str) -> int:
    """UPU S10 check digit for an 8-digit serial number."""
    total = sum(int(d) * w for d, w in zip(serial, _S10_WEIGHTS, strict=True))
    check = _S10_CHECK_ELEVEN - total % _S10_CHECK_ELEVEN
    if check == _S10_CHECK_TEN:
        return 0
    if check == _S10_CHECK_ELEVEN:
        return 5
    return check


def is_upu_s10(code: str) -> bool:
    """True for a well-formed international postal code with a valid check digit."""
    m = _S10_RE.fullmatch(code)
    return m is not None and s10_check_digit(m.group(2)) == int(m.group(3))


def s10_operator(code: str) -> str | None:
    """Name of the postal operator that issued an S10 code, when known."""
    if not is_upu_s10(code):
        return None
    return S10_OPERATORS.get(code[-2:])


def is_valid_tracking_number(code: str) -> bool:
    """True for a normalised code the bot can store: 5–40 letters and digits."""
    return bool(_CODE_RE.fullmatch(code))


def matches_specific_carrier(code: str, detector: _DetectorLike | None) -> bool:
    """True when a carrier-specific pattern (not the catch-all fallback) matches."""
    if detector is None:
        return False
    return any(getattr(t, "priority", 0) > 1 for t in detector.detect(code))


def is_known_code_format(code: str, detector: _DetectorLike | None) -> bool:
    """A code that is certainly a tracking number: a carrier pattern or a valid S10.

    Used where a false positive is costly (the reply to "what name for this
    parcel?" must not turn "AirPods2023" into a new parcel).
    """
    return is_upu_s10(code) or matches_specific_carrier(code, detector)


def looks_like_tracking(code: str, detector: _DetectorLike | None = None) -> bool:
    """Decide whether a word found in free text is a tracking code.

    Stricter than :func:`is_valid_tracking_number`: either a carrier pattern
    matches, or the word is 8–35 letters/digits with at least three digits.
    """
    if not is_valid_tracking_number(code):
        return False
    if is_known_code_format(code, detector):
        return True
    if not _FREE_TEXT_SHAPE.fullmatch(code):
        return False
    return sum(c.isdigit() for c in code) >= _FREE_TEXT_MIN_DIGITS


def extract_code_and_name(text: str, detector: _DetectorLike | None) -> tuple[str, str | None]:
    """Split a chat message into (normalised code, optional name).

    A code pasted with the spaces carriers print inside it (``"1Z 999 AA1 0123"``)
    is recognised as one code when the whole message normalises to a valid code;
    otherwise the first word is the code and the rest is the name.
    """
    stripped = text.strip()
    first, _, rest = stripped.partition(" ")
    first_code = normalize_tracking_number(first)
    if " " in stripped and not looks_like_tracking(first_code, detector):
        whole = normalize_tracking_number(stripped)
        if _is_spaced_code(stripped.split(), whole, detector):
            return whole, None
    return first_code, rest.strip() or None


_SPACED_GROUP_MAX = 6


def _is_spaced_code(groups: list[str], whole: str, detector: _DetectorLike | None) -> bool:
    """A code printed in short groups ("9400 1000 0000 …"), not a sentence with a number."""
    if any(len(g) > _SPACED_GROUP_MAX for g in groups) or not looks_like_tracking(whole, detector):
        return False
    if matches_specific_carrier(whole, detector):
        return True
    return sum(c.isdigit() for c in whole) * 2 >= len(whole)


def parse_bulk_codes(text: str, detector: _DetectorLike | None) -> list[tuple[str, str | None]]:
    """Codes from a multi-line message, one per line (``CODE [name]``).

    Returns an empty list unless at least two lines hold a code, so a single code
    followed by a multi-line note is still handled by the single-add path.
    """
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if len(lines) < 2:  # noqa: PLR2004
        return []
    found: list[tuple[str, str | None]] = []
    seen: set[str] = set()
    for line in lines:
        code, name = extract_code_and_name(line, detector)
        if looks_like_tracking(code, detector) and code not in seen:
            seen.add(code)
            found.append((code, clip_field("name", name)))
    return found if len(found) >= 2 else []  # noqa: PLR2004


def clip_field(name: str, value: str | None) -> str | None:
    """Trim a metadata value to its limit; empty becomes None."""
    if value is None:
        return None
    cleaned = " ".join(value.split()) if name != "notes" else value.strip()
    if not cleaned:
        return None
    return cleaned[: FIELD_LIMITS[name]]


def clean_tags(raw: str | Iterable[str] | None) -> list[str]:
    """Parse ``"vip, express #gift"`` or a list into lower-case, unique, capped tags."""
    if raw is None:
        return []
    parts = re.split(r"[,;#\n]+", raw) if isinstance(raw, str) else list(raw)
    tags: list[str] = []
    for part in parts:
        tag = " ".join(str(part).split()).lower()[:TAG_MAX_LEN]
        if tag and tag not in tags:
            tags.append(tag)
        if len(tags) >= MAX_TAGS:
            break
    return tags


@dataclass(slots=True)
class ShipmentInput:
    """User-provided data for a new shipment, before validation."""

    tracking_number: str
    name: str | None = None
    order_ref: str | None = None
    recipient: str | None = None
    destination: str | None = None
    notes: str | None = None
    tags: list[str] = field(default_factory=list)

    def to_parcel(self, user_id: int) -> Parcel:
        return Parcel(
            tracking_number=normalize_tracking_number(self.tracking_number),
            user_id=user_id,
            name=clip_field("name", self.name),
            order_ref=clip_field("order_ref", self.order_ref),
            recipient=clip_field("recipient", self.recipient),
            destination=clip_field("destination", self.destination),
            notes=clip_field("notes", self.notes),
            tags=clean_tags(self.tags),
        )


class AddOutcome(Enum):
    ADDED = "added"
    DUPLICATE = "duplicate"
    INVALID = "invalid"
    LIMIT = "limit"


class ShipmentRepo(Protocol):
    """The slice of ParcelRepository that add_shipment needs."""

    async def create(self, parcel: Parcel) -> Parcel | None: ...

    async def count_active_for_user(self, *, user_id: int) -> int: ...

    async def get_for_user(self, tracking_number: str, *, user_id: int) -> Parcel | None: ...


async def add_shipment(
    repo: ShipmentRepo, *, user_id: int, data: ShipmentInput, max_active: int
) -> tuple[AddOutcome, Parcel | None]:
    """Validate and store a shipment, enforcing the per-user active cap (0 = no cap)."""
    parcel = data.to_parcel(user_id)
    if not is_valid_tracking_number(parcel.tracking_number):
        return AddOutcome.INVALID, None
    if max_active > 0 and await repo.count_active_for_user(user_id=user_id) >= max_active:
        # Re-sending a code already tracked is a duplicate, not a cap violation.
        existing = await repo.get_for_user(parcel.tracking_number, user_id=user_id)
        if existing is not None and existing.is_active:
            return AddOutcome.DUPLICATE, None
        return AddOutcome.LIMIT, None
    created = await repo.create(parcel)
    if created is None:
        return AddOutcome.DUPLICATE, None
    return AddOutcome.ADDED, created


# --- status groups -------------------------------------------------------------


class StatusGroup(Enum):
    """Coarse buckets used by the dashboard, filters and statistics."""

    PENDING = "pending"
    TRANSIT = "transit"
    OUT_FOR_DELIVERY = "out_for_delivery"
    ATTENTION = "attention"
    DELIVERED = "delivered"


STATUS_GROUPS: dict[ShipmentStatus, StatusGroup] = {
    ShipmentStatus.NOT_FOUND: StatusGroup.PENDING,
    ShipmentStatus.INFO_RECEIVED: StatusGroup.PENDING,
    ShipmentStatus.PICKUP: StatusGroup.TRANSIT,
    ShipmentStatus.IN_TRANSIT: StatusGroup.TRANSIT,
    ShipmentStatus.CUSTOMS: StatusGroup.TRANSIT,
    ShipmentStatus.OUT_FOR_DELIVERY: StatusGroup.OUT_FOR_DELIVERY,
    ShipmentStatus.DELIVERED: StatusGroup.DELIVERED,
    ShipmentStatus.UNDELIVERED: StatusGroup.ATTENTION,
    ShipmentStatus.EXCEPTION: StatusGroup.ATTENTION,
    ShipmentStatus.ALERT: StatusGroup.ATTENTION,
    ShipmentStatus.RETURNED: StatusGroup.ATTENTION,
    ShipmentStatus.EXPIRED: StatusGroup.ATTENTION,
}

# Statuses after which the carrier reports nothing more: never "stalled".
FINAL_STATUSES: frozenset[ShipmentStatus] = frozenset(
    {ShipmentStatus.DELIVERED, ShipmentStatus.EXPIRED, ShipmentStatus.RETURNED}
)


def status_group(status: ShipmentStatus) -> StatusGroup:
    return STATUS_GROUPS.get(status, StatusGroup.PENDING)


def is_stalled(parcel: Parcel, now: datetime, stall_days: int) -> bool:
    """True when an active, unfinished shipment saw no carrier news for ``stall_days``."""
    if stall_days <= 0 or not parcel.is_active or parcel.status in FINAL_STATUSES:
        return False
    reference = parcel.last_change_at or parcel.created_at
    if reference is None:
        return False
    return now - reference >= timedelta(days=stall_days)


def needs_attention(parcel: Parcel, now: datetime, stall_days: int) -> bool:
    """Active shipments a seller should look at: carrier problems or stalled."""
    if not parcel.is_active:
        return False
    return status_group(parcel.status) is StatusGroup.ATTENTION or is_stalled(
        parcel, now, stall_days
    )


# Lifecycle steps shown as a progress bar (dashboard and public page).
PROGRESS_STEPS: tuple[ShipmentStatus, ...] = (
    ShipmentStatus.INFO_RECEIVED,
    ShipmentStatus.PICKUP,
    ShipmentStatus.IN_TRANSIT,
    ShipmentStatus.OUT_FOR_DELIVERY,
    ShipmentStatus.DELIVERED,
)
_PROGRESS_INDEX: dict[ShipmentStatus, int] = {
    ShipmentStatus.NOT_FOUND: -1,
    ShipmentStatus.INFO_RECEIVED: 0,
    ShipmentStatus.PICKUP: 1,
    ShipmentStatus.IN_TRANSIT: 2,
    ShipmentStatus.CUSTOMS: 2,
    ShipmentStatus.UNDELIVERED: 3,
    ShipmentStatus.EXCEPTION: 2,
    ShipmentStatus.ALERT: 2,
    ShipmentStatus.OUT_FOR_DELIVERY: 3,
    ShipmentStatus.DELIVERED: 4,
    ShipmentStatus.RETURNED: 2,
    ShipmentStatus.EXPIRED: 2,
}


def progress_index(status: ShipmentStatus) -> int:
    """Index of the last completed step in PROGRESS_STEPS (-1 = nothing yet)."""
    return _PROGRESS_INDEX.get(status, -1)
