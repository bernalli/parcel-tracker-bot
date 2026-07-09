"""Render a static map PNG with a transport-mode marker. Public XYZ tiles, no account."""

from __future__ import annotations

import io
import math
from functools import lru_cache
from pathlib import Path

from PIL import Image
from staticmap import IconMarker, Line, StaticMap

_MARKERS_DIR = Path(__file__).parent / "data" / "markers"
# CARTO voyager: English-first labels and @2x retina tiles (crisp text at any
# canvas size). OSM's default style labels places in the local script/language.
# Requires attribution: (c) OpenStreetMap contributors (c) CARTO.
_TILE_URL = "https://basemaps.cartocdn.com/rastertiles/voyager/{z}/{x}/{y}@2x.png"
_TILE_SIZE = 512  # @2x tiles are 512px; must match the url_template variant
_VALID_MODES = {"plane", "ship", "train", "truck", "parcel"}

_EARTH_RADIUS_KM = 6371.0
_DENSIFY_MAX_KM = 500.0

# Tiles are fetched at 2x the target size and downscaled: web-mercator tiles have
# no native anti-aliasing, so supersampling is what smooths lines and labels.
_SUPERSAMPLE = 2
_MAX_TILE_ZOOM = 19
_LINE_COLOR = "#1f6feb"
_LINE_WIDTH = 5  # at supersampled scale
_HALO_COLOR = "#ffffff"
_HALO_WIDTH = 10  # at supersampled scale


@lru_cache(maxsize=8)
def _icon_center(path: str) -> tuple[int, int]:
    """Anchor offset that pins the icon's centre on the coordinate."""
    with Image.open(path) as icon:
        return icon.width // 2, icon.height // 2


def _to_unit_vector(lat: float, lng: float) -> tuple[float, float, float]:
    lat_r, lng_r = math.radians(lat), math.radians(lng)
    return (
        math.cos(lat_r) * math.cos(lng_r),
        math.cos(lat_r) * math.sin(lng_r),
        math.sin(lat_r),
    )


def _haversine_km(a: tuple[float, float], b: tuple[float, float]) -> float:
    lat1, lng1 = math.radians(a[0]), math.radians(a[1])
    lat2, lng2 = math.radians(b[0]), math.radians(b[1])
    h = (
        math.sin((lat2 - lat1) / 2) ** 2
        + math.cos(lat1) * math.cos(lat2) * math.sin((lng2 - lng1) / 2) ** 2
    )
    return 2 * _EARTH_RADIUS_KM * math.asin(math.sqrt(h))


def _densify(
    waypoints: list[tuple[float, float]], *, max_km: float = _DENSIFY_MAX_KM
) -> list[tuple[float, float]]:
    """Insert great-circle intermediate points so no leg exceeds `max_km`.

    Long legs drawn as straight lines between projected endpoints look wrong on
    web-mercator maps (an intercontinental flight cutting across the map as a
    chord); slerping along the great circle renders the actual geodesic arc.
    """
    if len(waypoints) < 2:
        return list(waypoints)
    out: list[tuple[float, float]] = [waypoints[0]]
    for start, end in zip(waypoints, waypoints[1:], strict=False):
        distance = _haversine_km(start, end)
        if distance > max_km:
            ax, ay, az = _to_unit_vector(*start)
            bx, by, bz = _to_unit_vector(*end)
            omega = math.acos(max(-1.0, min(1.0, ax * bx + ay * by + az * bz)))
            if math.sin(omega) > 1e-9:
                segments = math.ceil(distance / max_km)
                for i in range(1, segments):
                    t = i / segments
                    ka = math.sin((1 - t) * omega) / math.sin(omega)
                    kb = math.sin(t * omega) / math.sin(omega)
                    x, y, z = ka * ax + kb * bx, ka * ay + kb * by, ka * az + kb * bz
                    out.append((math.degrees(math.asin(z)), math.degrees(math.atan2(y, x))))
        out.append(end)
    return out


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
        tile_size: int = _TILE_SIZE,
    ) -> None:
        self._ua = user_agent
        self._w = width
        self._h = height
        self._zoom = zoom
        self._tile_url = tile_url
        self._tile_size = tile_size

    def _marker_path(self, mode: str) -> str:
        chosen = mode if mode in _VALID_MODES else "parcel"
        return str(_MARKERS_DIR / f"{chosen}.png")

    def _supersampled_map(self) -> StaticMap:
        return StaticMap(
            self._w * _SUPERSAMPLE,
            self._h * _SUPERSAMPLE,
            url_template=self._tile_url,
            tile_size=self._tile_size,
            headers={"User-Agent": self._ua},
        )

    def _finish(self, image: Image.Image) -> bytes:
        """Downscale the supersampled render to target size and encode as PNG."""
        image = image.resize((self._w, self._h), Image.Resampling.LANCZOS)
        buf = io.BytesIO()
        image.save(buf, format="PNG")
        return buf.getvalue()

    def _add_mode_marker(self, smap: StaticMap, lonlat: tuple[float, float], mode: str) -> None:
        icon_path = self._marker_path(mode)
        offset_x, offset_y = _icon_center(icon_path)
        smap.add_marker(IconMarker(lonlat, icon_path, offset_x, offset_y))

    def render(self, *, lat: float, lng: float, mode: str) -> bytes:
        """Return PNG bytes for a map centred on (lat, lng) with a mode marker."""
        smap = self._supersampled_map()
        # staticmap marker coords are (lon, lat).
        self._add_mode_marker(smap, (lng, lat), mode)
        # zoom+1 on a 2x canvas keeps the same geographic extent at double resolution.
        image = smap.render(zoom=min(self._zoom + 1, _MAX_TILE_ZOOM))
        return self._finish(image)

    def render_route(self, waypoints: list[tuple[float, float]], *, mode: str) -> bytes:
        """Render a PNG with a geodesic polyline through `waypoints` (lat,lng order)
        and a mode icon on the final point. With a single waypoint, only the icon."""
        if not waypoints:
            raise ValueError("render_route requires at least one waypoint")
        smap = self._supersampled_map()
        lonlat = [(lng, lat) for (lat, lng) in _densify(waypoints)]
        if len(lonlat) >= 2:  # noqa: PLR2004
            smap.add_line(Line(lonlat, _HALO_COLOR, _HALO_WIDTH))
            smap.add_line(Line(lonlat, _LINE_COLOR, _LINE_WIDTH))
        self._add_mode_marker(smap, lonlat[-1], mode)
        image = smap.render()  # auto-fit to markers/lines
        return self._finish(image)
