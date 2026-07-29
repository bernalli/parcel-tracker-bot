"""Best-effort extraction of a place hint from a free-text tracking description.

Heuristic and intentionally conservative: returns a candidate string that the
strict Geocoder may resolve. Callers MUST geocode the result and discard misses,
so a wrong guess yields no waypoint rather than a wrong location. This is the
fallback for carriers that put the place in the event text but not in a
dedicated location field.
"""

from __future__ import annotations

import re

# A place tends to follow a locative marker. Multi-word Italian phrases ending
# in "a" come first so they win over the bare prepositions that prefix them.
_MARKERS = re.compile(
    r"\b(?:in transito a|consegnato a|arrivato a|presso|at|in|to)\s+(.+)$",
    re.IGNORECASE,
)


def extract_location_hint(description: str | None) -> str | None:
    """Return a candidate place string mined from a description, or None."""
    if not description:
        return None
    match = _MARKERS.search(description.strip())
    if not match:
        return None
    tail = match.group(1).strip(" .,;:")
    return tail or None
