"""The committed gettext catalogs stay in sync with the strings in the code."""

from __future__ import annotations

from pathlib import Path

import pytest
from babel.messages.extract import extract_from_dir
from babel.messages.pofile import read_po

SRC = Path(__file__).resolve().parents[3] / "src" / "parcel_tracker"
LOCALE = SRC / "i18n" / "locale"
LOCALES = sorted(p.parent.parent.name for p in LOCALE.glob("*/LC_MESSAGES/messages.po"))


def _code_msgids() -> set[str]:
    ids: set[str] = set()
    for _file, _line, message, _comments, _ctx in extract_from_dir(
        str(SRC),
        method_map=[("**.py", "python")],
        keywords={"_": None, "ngettext": (1, 2)},
    ):
        ids.add(message if isinstance(message, str) else message[0])
    return ids


CODE = _code_msgids()


def _ids(path: Path) -> dict[str, str]:
    with path.open("rb") as fh:
        catalog = read_po(fh)
    return {
        m.id if isinstance(m.id, str) else m.id[0]: (
            m.string if isinstance(m.string, str) else m.string[0]
        )
        for m in catalog
        if m.id
    }


def test_template_matches_code() -> None:
    pot = set(_ids(LOCALE / "messages.pot"))
    assert sorted(CODE - pot) == [], "strings missing from messages.pot (run pybabel extract)"
    assert sorted(pot - CODE) == [], "stale strings in messages.pot"


@pytest.mark.parametrize("locale", LOCALES)
def test_locale_has_no_orphans(locale: str) -> None:
    po = _ids(LOCALE / locale / "LC_MESSAGES" / "messages.po")
    assert sorted(set(po) - CODE) == [], f"{locale}: entries no longer used by the code"


def test_italian_translates_every_string() -> None:
    po = _ids(LOCALE / "it" / "LC_MESSAGES" / "messages.po")
    missing = sorted(i for i in CODE if not po.get(i))
    assert missing == []


@pytest.mark.parametrize(
    "module",
    ["parcel_tracker.bot.notify_commands", "parcel_tracker.bot.health_commands"],
)
def test_user_facing_commands_are_translatable(module: str) -> None:
    import importlib
    import inspect

    source = inspect.getsource(importlib.import_module(module))
    assert "from parcel_tracker.i18n import _" in source
