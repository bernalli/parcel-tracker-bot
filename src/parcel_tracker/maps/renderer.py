"""Render a static map PNG with a transport-mode marker. OSM tiles, no account."""

from __future__ import annotations

import io
from pathlib import Path

from staticmap import IconMarker, StaticMap

_MARKERS_DIR = Path(__file__).parent / "data" / "markers"
_TILE_URL = "https://tile.openstreetmap.org/{z}/{x}/{y}.png"
_VALID_MODES = {"plane", "ship", "train", "truck", "parcel"}


class MapRenderer:
    """Builds a small PNG map centred on a coordinate with a mode icon."""

    def __init__(
        self,
        *,
        user_agent: str,
        width: int = 600,
        height: int = 400,
        zoom: int = 6,
        tile_url: str = _TILE_URL,
    ) -> None:
        self._ua = user_agent
        self._w = width
        self._h = height
        self._zoom = zoom
        self._tile_url = tile_url

    def _marker_path(self, mode: str) -> str:
        chosen = mode if mode in _VALID_MODES else "parcel"
        return str(_MARKERS_DIR / f"{chosen}.png")

    def render(self, *, lat: float, lng: float, mode: str) -> bytes:
        """Return PNG bytes for a map centred on (lat, lng) with a mode marker."""
        smap = StaticMap(
            self._w,
            self._h,
            url_template=self._tile_url,
            headers={"User-Agent": self._ua},
        )
        # staticmap marker coords are (lon, lat).
        smap.add_marker(IconMarker((lng, lat), self._marker_path(mode), 20, 0))
        image = smap.render(zoom=self._zoom)
        buf = io.BytesIO()
        image.save(buf, format="PNG")
        return buf.getvalue()
