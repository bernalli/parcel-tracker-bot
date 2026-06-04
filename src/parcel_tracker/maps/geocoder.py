"""Offline city -> (lat, lng) lookup backed by a GeoNames-derived TSV. No network.

TSV columns (tab-separated): name, asciiname, alternatenames(comma-sep), lat, lng, country_code.
Primary, ascii, and a bounded set of word-like alternate names are all indexed, so
both English ("Milan") and local ("Milano") names resolve.
"""

from __future__ import annotations

import unicodedata
from pathlib import Path

_MAX_ALTERNATES = 15  # bound per-city alternates to keep the in-memory index reasonable


def _norm(s: str) -> str:
    """Lowercase + strip accents for resilient matching."""
    nfkd = unicodedata.normalize("NFKD", s.strip().lower())
    return "".join(c for c in nfkd if not unicodedata.combining(c))


def _is_wordlike(s: str) -> bool:
    """Keep plausible place names; drop codes, ids, urls, numerics."""
    s = s.strip()
    if not (2 <= len(s) <= 40):
        return False
    if any(ch.isdigit() for ch in s):
        return False
    return any(ch.isalpha() for ch in s)


class Geocoder:
    """Loads a 6-column GeoNames-derived TSV into an in-memory name->coord index."""

    def __init__(self, dataset_path: Path) -> None:
        self._by_city_country: dict[tuple[str, str], tuple[float, float]] = {}
        self._by_city: dict[str, tuple[float, float]] = {}
        for raw in dataset_path.read_text(encoding="utf-8").splitlines():
            if not raw or raw.startswith("#"):
                continue
            parts = raw.split("\t")
            if len(parts) < 6:
                continue
            name, ascii_name, alternates, lat_s, lng_s, cc = parts[:6]
            try:
                coord = (float(lat_s), float(lng_s))
            except ValueError:
                continue
            cc_n = _norm(cc)
            names: set[str] = {name, ascii_name}
            count = 0
            for alt in alternates.split(","):
                if count >= _MAX_ALTERNATES:
                    break
                if _is_wordlike(alt):
                    names.add(alt)
                    count += 1
            for n in {_norm(x) for x in names if x}:
                self._by_city_country.setdefault((n, cc_n), coord)
                self._by_city.setdefault(n, coord)

    def geocode(self, location: str | None) -> tuple[float, float] | None:
        """Resolve 'City, Country' (or 'City') to coordinates; None if unknown."""
        if not location:
            return None
        head = location.split(",")
        city = _norm(head[0])
        if len(head) >= 2:
            country = _norm(head[-1])
            hit = self._by_city_country.get((city, country))
            if hit is not None:
                return hit
        return self._by_city.get(city)
