#!/usr/bin/env python3
"""Maintain the gettext catalogs.

    python scripts/i18n.py update            # re-extract strings, merge into every .po
    python scripts/i18n.py missing it        # untranslated msgids of a locale, as JSON
    python scripts/i18n.py apply it file.json  # set translations from {msgid: msgstr}
    python scripts/i18n.py init es           # start a new locale from the template

Strings are extracted from the Python sources (``_``, ``_n``) and the web
dashboard's Jinja templates. Existing translations are kept; strings that left the
code are dropped. Run ``python -m parcel_tracker.i18n.build`` afterwards to
compile the ``.mo`` files.
"""

from __future__ import annotations

import json
import sys
from datetime import UTC, datetime
from pathlib import Path

from babel.messages.catalog import Catalog
from babel.messages.extract import extract_from_dir
from babel.messages.pofile import read_po, write_po

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "src" / "parcel_tracker"
LOCALE = SRC / "i18n" / "locale"
POT = LOCALE / "messages.pot"

METHOD_MAP = [
    ("**/templates/**.html", "jinja2"),
    ("**.py", "python"),
]
OPTIONS = {"**/templates/**.html": {"extensions": "jinja2.ext.i18n", "trimmed": "true"}}
KEYWORDS = {"_": None, "_n": (1, 2), "ngettext": (1, 2), "gettext": None}


def extract() -> Catalog:
    catalog = Catalog(
        project="parcel-tracker-bot",
        msgid_bugs_address="https://github.com/bernalli/parcel-tracker-bot/issues",
        copyright_holder="bernalli",
        creation_date=datetime(2026, 1, 1, tzinfo=UTC),
    )
    for filename, lineno, message, comments, context in extract_from_dir(
        str(SRC), method_map=METHOD_MAP, options_map=OPTIONS, keywords=KEYWORDS
    ):
        path = (SRC / filename).relative_to(ROOT).as_posix()
        catalog.add(
            message,
            None,
            [(path, lineno)],
            auto_comments=comments,
            context=context,
        )
    return catalog


def _write(path: Path, catalog: Catalog) -> None:
    with path.open("wb") as fh:
        write_po(fh, catalog, width=100, omit_header=False, ignore_obsolete=True, sort_output=True)


def _read(path: Path) -> Catalog:
    with path.open("rb") as fh:
        return read_po(fh)


def _po(locale: str) -> Path:
    return LOCALE / locale / "LC_MESSAGES" / "messages.po"


def update() -> None:
    template = extract()
    _write(POT, template)
    for po_path in sorted(LOCALE.glob("*/LC_MESSAGES/messages.po")):
        catalog = _read(po_path)
        catalog.update(template, no_fuzzy_matching=True)
        _write(po_path, catalog)
        print(f"updated {po_path.relative_to(ROOT)}")


def missing(locale: str) -> None:
    catalog = _read(_po(locale))
    todo = {}
    for message in catalog:
        if not message.id:
            continue
        if isinstance(message.id, tuple):
            strings = message.string if isinstance(message.string, tuple) else ()
            if not all(strings):
                todo[message.id[0]] = list(message.id)
        elif not message.string:
            todo[message.id] = ""
    json.dump(todo, sys.stdout, ensure_ascii=False, indent=2)
    print()


def apply(locale: str, mapping_file: str) -> None:
    mapping = json.loads(Path(mapping_file).read_text(encoding="utf-8"))
    po_path = _po(locale)
    catalog = _read(po_path)
    applied = 0
    for message in catalog:
        key = message.id[0] if isinstance(message.id, tuple) else message.id
        if key in mapping:
            value = mapping[key]
            message.string = tuple(value) if isinstance(message.id, tuple) else value
            message.flags.discard("fuzzy")
            applied += 1
    _write(po_path, catalog)
    print(f"{locale}: applied {applied}/{len(mapping)} translations")


def init(locale: str) -> None:
    po_path = _po(locale)
    if po_path.exists():
        raise SystemExit(f"{po_path} already exists")
    po_path.parent.mkdir(parents=True, exist_ok=True)
    template = _read(POT)
    catalog = Catalog(locale=locale, project="parcel-tracker-bot")
    catalog.update(template, no_fuzzy_matching=True)
    _write(po_path, catalog)
    print(f"created {po_path.relative_to(ROOT)}")


def main(argv: list[str]) -> None:
    if not argv:
        raise SystemExit(__doc__)
    command, *args = argv
    if command == "update":
        update()
    elif command == "missing" and len(args) == 1:
        missing(args[0])
    elif command == "apply" and len(args) == 2:  # noqa: PLR2004
        apply(args[0], args[1])
    elif command == "init" and len(args) == 1:
        init(args[0])
    else:
        raise SystemExit(__doc__)


if __name__ == "__main__":
    main(sys.argv[1:])
