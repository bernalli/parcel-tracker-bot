from __future__ import annotations

from unittest.mock import MagicMock, patch

from parcel_tracker.maps.renderer import MapRenderer


def test_render_route_draws_line_and_icon_for_multiple_points() -> None:
    with (
        patch("parcel_tracker.maps.renderer.StaticMap") as smap_cls,
        patch("parcel_tracker.maps.renderer.Line") as line_cls,
        patch("parcel_tracker.maps.renderer.IconMarker") as icon_cls,
    ):
        smap = smap_cls.return_value
        img = MagicMock()
        smap.render.return_value = img
        r = MapRenderer(user_agent="ua")
        r.render_route([(45.46, 9.19), (41.9, 12.5)], mode="truck")
        # one polyline added, one icon marker on the LAST point (lon, lat order)
        assert line_cls.called
        icon_args = icon_cls.call_args.args
        assert icon_args[0] == (12.5, 41.9)
        assert smap.add_line.called
        assert smap.add_marker.called


def test_render_route_single_point_only_marker_no_line() -> None:
    with (
        patch("parcel_tracker.maps.renderer.StaticMap") as smap_cls,
        patch("parcel_tracker.maps.renderer.Line") as line_cls,
        patch("parcel_tracker.maps.renderer.IconMarker"),
    ):
        smap = smap_cls.return_value
        smap.render.return_value = MagicMock()
        r = MapRenderer(user_agent="ua")
        r.render_route([(45.46, 9.19)], mode="parcel")
        assert not line_cls.called
        assert smap.add_marker.called
