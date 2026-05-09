from pathlib import Path

import pytest

from parcel_tracker.bot import messages
from parcel_tracker.i18n import Translator, set_default_translator

LOCALE_ROOT = Path("src/parcel_tracker/i18n/locale")


@pytest.mark.integration
def test_messages_render_in_english_when_locale_en() -> None:
    set_default_translator(Translator(locale="en", locale_dir=LOCALE_ROOT))
    assert "Parcel added" in messages.parcel_added(name="X")
    assert "are not authorised" in messages.unauthorized()


@pytest.mark.integration
def test_messages_render_in_italian_when_locale_it() -> None:
    set_default_translator(Translator(locale="it", locale_dir=LOCALE_ROOT))
    assert "Pacco aggiunto" in messages.parcel_added(name="X")
    assert "Non sei autorizzato" in messages.unauthorized()
    # restore default for subsequent tests
    set_default_translator(Translator(locale="en", locale_dir=LOCALE_ROOT))
