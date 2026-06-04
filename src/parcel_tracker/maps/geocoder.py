"""Offline city → (lat, lng) lookup backed by a GeoNames-derived TSV. No network."""

from __future__ import annotations

import unicodedata
from pathlib import Path


def _norm(s: str) -> str:
    """Lowercase + strip accents for resilient matching."""
    nfkd = unicodedata.normalize("NFKD", s.strip().lower())
    return "".join(c for c in nfkd if not unicodedata.combining(c))


class Geocoder:
    """Loads a TSV (name, asciiname, lat, lng, country_code) into an in-memory index."""

    def __init__(self, dataset_path: Path) -> None:
        self._by_city_country: dict[tuple[str, str], tuple[float, float]] = {}
        self._by_city: dict[str, tuple[float, float]] = {}
        for raw in dataset_path.read_text(encoding="utf-8").splitlines():
            if not raw or raw.startswith("#"):
                continue
            parts = raw.split("\t")
            if len(parts) < 5:
                continue
            name, ascii_name, lat_s, lng_s, cc = parts[:5]
            try:
                coord = (float(lat_s), float(lng_s))
            except ValueError:
                continue
            cc_n = _norm(cc)
            for n in {_norm(name), _norm(ascii_name)}:
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
