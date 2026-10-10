"""Offline city -> (lat, lng) lookup backed by a GeoNames-derived TSV. No network.

TSV columns (tab-separated): name, asciiname, alternatenames(comma-sep), lat, lng, country_code.
Primary, ascii, and a bounded set of word-like alternate names are all indexed, so
both English ("Milan") and local ("Milano") names resolve.
"""

from __future__ import annotations

import re
import unicodedata
from pathlib import Path

_MAX_ALTERNATES = 15  # bound per-city alternates to keep the in-memory index reasonable

_PAREN_RE = re.compile(r"\([^)]*\)")  # "(134)", "(MI)"
_LEADING_CODE_RE = re.compile(r"^\d{3,6}\b\s*")  # postal / leading numeric code
_GENERIC_SUFFIXES = ("city", "town")
_GENERIC_TOKENS = {
    "hub",
    "facility",
    "depot",
    "warehouse",
    "sorting",
    "center",
    "centre",
    "smistamento",
    "filiale",
    "deposito",
    "ufficio",
    "aeroporto",
    "airport",
}
_PREFIXES = (
    "filiale di ",
    "filiale ",
    "hub ",
    "centro di smistamento ",
    "centro smistamento ",
    "deposito ",
    "ufficio di ",
    "ufficio ",
    "sorting center ",
    "sorting centre ",
    "facility ",
)
# USPS state/territory abbreviations. US carriers print "CITY, ST" or
# "CITY, ST, US"; several of these are also ISO country codes (CA, DE, GA, IN…),
# so a bare two-letter suffix from a US carrier must not be read as a country.
_US_STATES = frozenset(
    "AL AK AZ AR CA CO CT DE DC FL GA HI ID IL IN IA KS KY LA ME MD MA MI MN MS MO MT "
    "NE NV NH NJ NM NY NC ND OH OK OR PA RI SC SD TN TX UT VT VA WA WV WI WY PR".lower().split()
)

_COUNTRY_TO_ISO = {
    "italy": "it",
    "italia": "it",
    "united states": "us",
    "united states of america": "us",
    "usa": "us",
    "u.s.a.": "us",
    "united kingdom": "gb",
    "great britain": "gb",
    "uk": "gb",
    "germany": "de",
    "deutschland": "de",
    "france": "fr",
    "spain": "es",
    "espana": "es",
    "netherlands": "nl",
    "belgium": "be",
    "switzerland": "ch",
    "austria": "at",
    "portugal": "pt",
    "china": "cn",
    "japan": "jp",
    "canada": "ca",
    "australia": "au",
    "brazil": "br",
    "brasil": "br",
}


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


_Entry = tuple[float, float, int]


class Geocoder:
    """Loads a 6-column GeoNames-derived TSV into an in-memory name->coord index."""

    def __init__(self, dataset_path: Path) -> None:
        # Values are (lat, lng, rank); rows are sorted by population, so a lower
        # rank is a larger place. One tuple per row, shared by all its keys.
        self._by_city_country: dict[tuple[str, str], _Entry] = {}
        self._by_city: dict[str, _Entry] = {}
        for rank, raw in enumerate(dataset_path.read_text(encoding="utf-8").splitlines()):
            if not raw or raw.startswith("#"):
                continue
            parts = raw.split("\t")
            if len(parts) < 6:
                continue
            name, ascii_name, alternates, lat_s, lng_s, cc = parts[:6]
            try:
                coord: _Entry = (float(lat_s), float(lng_s), rank)
            except ValueError:
                continue
            cc_n = _norm(cc)
            for n in self._row_keys(name, ascii_name, alternates):
                self._by_city_country.setdefault((n, cc_n), coord)
                self._by_city.setdefault(n, coord)

    @staticmethod
    def _row_keys(name: str, ascii_name: str, alternates: str) -> set[str]:
        """Normalised lookup keys for one TSV row: primary, ascii, a bounded set
        of word-like alternates, plus generic-suffix-stripped variants."""
        names: set[str] = {name, ascii_name}
        count = 0
        for alt in alternates.split(","):
            if count >= _MAX_ALTERNATES:
                break
            if _is_wordlike(alt):
                names.add(alt)
                count += 1
        keys: set[str] = set()
        for x in names:
            if not x:
                continue
            nx = _norm(x)
            keys.add(nx)
            for suf in _GENERIC_SUFFIXES:
                if nx.endswith(" " + suf):
                    keys.add(nx[: -(len(suf) + 1)].strip())
        return keys

    @staticmethod
    def _country_iso(segment: str) -> str | None:
        """Map a trailing segment to an ISO-2 country code, or None if it is not
        a recognisable country (name or 2-letter code)."""
        n = _norm(segment)
        if n in _COUNTRY_TO_ISO:
            return _COUNTRY_TO_ISO[n]
        if len(n) == 2 and n.isalpha():
            return n
        return None

    @staticmethod
    def _clean_variants(segment: str) -> list[str]:
        """Progressively cleaned lookup keys for a city segment, most specific first."""
        base = " ".join(_norm(segment).split())
        out: list[str] = []

        def add(v: str) -> None:
            v = " ".join(v.split())
            if v and v not in out:
                out.append(v)

        add(base)
        no_paren = " ".join(_PAREN_RE.sub(" ", base).split())
        add(no_paren)
        add(_LEADING_CODE_RE.sub("", no_paren))
        for p in _PREFIXES:
            if no_paren.startswith(p):
                add(no_paren[len(p) :])
        parts = no_paren.split()
        if len(parts) >= 2 and len(parts[-1]) == 2 and parts[-1].isalpha():  # noqa: PLR2004
            add(" ".join(parts[:-1]))
        kept = [t for t in parts if t not in _GENERIC_TOKENS]
        if kept and kept != parts:
            add(" ".join(kept))
        for suf in _GENERIC_SUFFIXES:
            if base.endswith(" " + suf):
                add(base[: -(len(suf) + 1)])
        return out

    def geocode(self, location: str | None) -> tuple[float, float] | None:
        """Resolve a courier location string to coordinates; None if unknown.

        Tolerates decorations ("Cattolica (134)", "Bologna BO", "Filiale di X"),
        tries every comma segment as a candidate city, and honours an explicit
        country (never silently placing the parcel in a different country)."""
        if not location:
            return None
        segments = [s for s in (seg.strip() for seg in location.split(",")) if s]
        if not segments:
            return None
        last = _norm(segments[-1])
        country = self._country_iso(segments[-1]) if len(segments) >= 2 else None  # noqa: PLR2004
        candidates = segments[:-1] if country else segments
        # "CITY, ST" from a US carrier: the two letters may be a state that is also
        # a country code (CA, DE, IN…), so both readings are considered.
        state_or_country = country is not None and len(last) == 2 and last in _US_STATES  # noqa: PLR2004
        if country == "us" and len(candidates) >= 2 and _norm(candidates[-1]) in _US_STATES:  # noqa: PLR2004
            candidates = candidates[:-1]  # "CITY, ST, US": the state is not a city
        for seg in candidates:
            for variant in self._clean_variants(seg):
                hit = self._lookup(variant, country, also_us=state_or_country)
                if hit is not None:
                    return hit
        return None

    def _lookup(
        self, variant: str, country: str | None, *, also_us: bool
    ) -> tuple[float, float] | None:
        if country is None:
            entry = self._by_city.get(variant)
            return (entry[0], entry[1]) if entry else None
        entry = self._by_city_country.get((variant, country))
        if also_us:
            us = self._by_city_country.get((variant, "us"))
            # The larger place wins: "Toronto, CA" stays in Canada, while
            # "Sacramento, CA" (no such city in Canada) lands in California.
            if us is not None and (entry is None or us[2] < entry[2]):
                entry = us
        return (entry[0], entry[1]) if entry else None
