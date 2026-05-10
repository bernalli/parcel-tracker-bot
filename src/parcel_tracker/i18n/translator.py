"""Gettext-based translator with English-fallback semantics."""

from __future__ import annotations

import gettext
from pathlib import Path
from typing import Final

DEFAULT_DOMAIN: Final = "messages"


class Translator:
    """Thin wrapper around `gettext.GNUTranslations` with English fallback."""

    def __init__(
        self,
        locale: str,
        locale_dir: Path,
        domain: str = DEFAULT_DOMAIN,
    ) -> None:
        if not locale_dir.is_dir():
            raise FileNotFoundError(locale_dir)
        self.locale = locale
        self._domain = domain
        self._locale_dir = locale_dir
        self._gnu = gettext.translation(
            domain=domain,
            localedir=str(locale_dir),
            languages=[locale],
            fallback=True,
        )

    def gettext(self, msgid: str) -> str:
        return self._gnu.gettext(msgid)

    def ngettext(self, msgid: str, msgid_plural: str, n: int) -> str:
        return self._gnu.ngettext(msgid, msgid_plural, n)


def available_locales(locale_dir: Path) -> list[str]:
    """List locale codes for which a compiled `messages.mo` exists.

    Checks the binary catalog (.mo) — what gettext actually loads at runtime —
    not the source (.po), which is excluded from distributed package-data.
    """
    if not locale_dir.is_dir():
        return []
    return sorted(
        d.name
        for d in locale_dir.iterdir()
        if d.is_dir() and (d / "LC_MESSAGES" / "messages.mo").is_file()
    )


_default: Translator | None = None


def set_default_translator(translator: Translator) -> None:
    global _default  # noqa: PLW0603
    _default = translator


def get_default_translator() -> Translator:
    if _default is None:
        raise RuntimeError("Translator not initialised; call set_default_translator() first")
    return _default
