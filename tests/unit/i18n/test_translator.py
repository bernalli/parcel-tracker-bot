"""Tests for the gettext translator wrapper."""

from __future__ import annotations

from pathlib import Path

import pytest

from parcel_tracker.i18n import (
    Translator,
    available_locales,
    get_default_translator,
    set_default_translator,
)


def _locale_root() -> Path:
    return Path(__file__).resolve().parents[3] / "src" / "parcel_tracker" / "i18n" / "locale"


def test_translator_falls_back_to_msgid_when_locale_missing() -> None:
    t = Translator(locale="zz", locale_dir=_locale_root())
    assert t.gettext("Welcome") == "Welcome"


def test_translator_returns_msgid_for_english() -> None:
    t = Translator(locale="en", locale_dir=_locale_root())
    assert t.gettext("Welcome") == "Welcome"


def test_translator_returns_translation_for_italian() -> None:
    t = Translator(locale="it", locale_dir=_locale_root())
    # Use a real msgid we know is translated.
    out = t.gettext("⛔ You are not authorised to use this bot.")
    assert "Non sei autorizzato" in out


def test_translator_supports_ngettext() -> None:
    t = Translator(locale="en", locale_dir=_locale_root())
    assert t.ngettext("{count} parcel", "{count} parcels", 1) == "{count} parcel"
    assert t.ngettext("{count} parcel", "{count} parcels", 5) == "{count} parcels"


def test_available_locales_returns_empty_when_none_initialised(tmp_path: Path) -> None:
    assert available_locales(tmp_path) == []


def test_default_translator_raises_until_set() -> None:
    import parcel_tracker.i18n.translator as translator_module

    translator_module._default = None  # noqa: SLF001
    with pytest.raises(RuntimeError, match="not initialised"):
        get_default_translator()


def test_set_default_translator_overrides_locale() -> None:
    set_default_translator(Translator(locale="en", locale_dir=_locale_root()))
    assert get_default_translator().locale == "en"


def test_translator_locale_dir_must_exist() -> None:
    with pytest.raises(FileNotFoundError):
        Translator(locale="en", locale_dir=Path("/nonexistent"))
