# src/parcel_tracker/i18n/build.py
"""Compile every `messages.po` under `locale/` into `messages.mo`.

Run as `python -m parcel_tracker.i18n.build`. Idempotent.
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

from babel.messages.mofile import write_mo
from babel.messages.pofile import read_po

logger = logging.getLogger(__name__)

LOCALE_DIR = Path(__file__).parent / "locale"


def compile_all() -> int:
    if not LOCALE_DIR.is_dir():
        logger.error("locale dir missing: %s", LOCALE_DIR)
        return 1

    count = 0
    for po_path in sorted(LOCALE_DIR.rglob("LC_MESSAGES/messages.po")):
        mo_path = po_path.with_suffix(".mo")
        with po_path.open("rb") as fh:
            catalog = read_po(fh)
        with mo_path.open("wb") as fh:
            write_mo(fh, catalog, use_fuzzy=True)
        logger.info("compiled %s → %s", po_path, mo_path)
        count += 1

    if count == 0:
        logger.error("no messages.po files found under %s", LOCALE_DIR)
        return 1
    return 0


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    sys.exit(compile_all())


if __name__ == "__main__":
    main()
