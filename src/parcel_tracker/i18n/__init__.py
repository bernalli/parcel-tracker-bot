"""i18n package — public surface."""

from parcel_tracker.i18n.translator import (
    Translator,
    available_locales,
    get_default_translator,
    set_default_translator,
)

__all__ = [
    "Translator",
    "_",
    "_n",
    "available_locales",
    "get_default_translator",
    "set_default_translator",
]


def _(msgid: str) -> str:
    """Translate `msgid` using the currently-installed default translator."""
    return get_default_translator().gettext(msgid)


def _n(singular: str, plural: str, n: int) -> str:
    """Translate (singular/plural) using the default translator."""
    return get_default_translator().ngettext(singular, plural, n)
