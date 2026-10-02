"""i18n package — public surface."""

from pathlib import Path

from parcel_tracker.i18n.translator import (
    Translator,
    activate,
    available_locales,
    current_translator,
    get_default_translator,
    set_default_translator,
    translator_for,
    using,
)

LOCALE_DIR = Path(__file__).parent / "locale"

__all__ = [
    "LOCALE_DIR",
    "Translator",
    "activate",
    "current_translator",
    "translator_for",
    "using",
    "_",
    "_n",
    "available_locales",
    "get_default_translator",
    "set_default_translator",
]


def _(msgid: str) -> str:
    """Translate `msgid` in the current user's language (default translator otherwise)."""
    return current_translator().gettext(msgid)


def _n(singular: str, plural: str, n: int) -> str:
    """Translate (singular/plural) in the current user's language."""
    return current_translator().ngettext(singular, plural, n)
