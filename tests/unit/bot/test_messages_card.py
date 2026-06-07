from __future__ import annotations

from datetime import UTC, datetime

from parcel_tracker.bot import messages
from parcel_tracker.db.models import Parcel, ShipmentStatus


def _parcel(**kw: object) -> Parcel:
    base: dict = {"tracking_number": "1Z999AA10123456784", "user_id": 1}
    base.update(kw)
    return Parcel(**base)  # type: ignore[arg-type]


def test_card_shows_name_code_status_carrier() -> None:
    p = _parcel(
        name="iPhone 15",
        carrier_name="UPS",
        status=ShipmentStatus.IN_TRANSIT,
    )
    card = messages.parcel_detail_card(p)
    assert "<b>iPhone 15</b>" in card
    assert "<code>1Z999AA10123456784</code>" in card
    assert "🚚" in card  # status emoji
    assert "UPS" in card


def test_card_falls_back_to_code_as_title() -> None:
    card = messages.parcel_detail_card(_parcel())
    assert card.count("1Z999AA10123456784") == 2  # titolo + riga codice, non di più


def test_card_optional_rows_absent_when_null() -> None:
    card = messages.parcel_detail_card(_parcel())
    assert "📍" not in card
    assert "🛈" not in card


def test_card_location_event_and_check_time() -> None:
    p = _parcel(
        last_location="Milano, IT",
        last_event="Arrived at facility",
        last_event_time="2026-06-06T22:41:00+02:00",
        last_check_at=datetime(2026, 6, 7, 10, 40, tzinfo=UTC),
    )
    card = messages.parcel_detail_card(p)
    assert "📍 Milano, IT" in card
    assert "Arrived at facility" in card
    assert "06/06/2026" in card  # last_event_time formattato
    assert "/2026" in card.splitlines()[-1]  # riga last check presente


def test_card_escapes_html_in_name_and_event() -> None:
    p = _parcel(name="<b>evil</b>", last_event="a <script> tag")
    card = messages.parcel_detail_card(p)
    assert "<b>evil</b>" not in card          # il nome è escapato
    assert "&lt;b&gt;evil&lt;/b&gt;" in card
    assert "&lt;script&gt;" in card


def test_parcel_added_and_renamed_escape_name() -> None:
    assert "&lt;x&gt;" in messages.parcel_added("<x>")
    assert "&lt;x&gt;" in messages.parcel_renamed("TN1", "<x>")


def test_delivery_confirm_prompt_without_title_shows_code_once() -> None:
    text = messages.delivery_confirm_prompt(None, "TN12345678")
    assert text.count("TN12345678") == 1


def test_new_prompt_messages_exist() -> None:
    assert messages.ask_parcel_name()
    assert messages.refresh_in_progress()
    assert messages.refresh_quarantined()
    assert messages.refresh_failed()
    assert messages.name_hint()
