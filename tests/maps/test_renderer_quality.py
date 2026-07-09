from __future__ import annotations

from unittest.mock import MagicMock, patch

from PIL import Image

from parcel_tracker.maps.renderer import _MARKERS_DIR, MapRenderer

SHENZHEN = (22.5431, 114.0579)
DUBAI = (25.2532, 55.3657)
MILAN = (45.4642, 9.1900)


def _patched_renderer() -> tuple[MagicMock, MagicMock, MagicMock, MagicMock]:
    smap_cls = patch("parcel_tracker.maps.renderer.StaticMap").start()
    line_cls = patch("parcel_tracker.maps.renderer.Line").start()
    icon_cls = patch("parcel_tracker.maps.renderer.IconMarker").start()
    smap = smap_cls.return_value
    img = MagicMock()
    smap.render.return_value = img
    return smap_cls, line_cls, icon_cls, img


def teardown_function() -> None:
    patch.stopall()


def test_render_route_supersamples_canvas_and_downscales() -> None:
    smap_cls, _, _, img = _patched_renderer()
    r = MapRenderer(user_agent="ua", width=600, height=400)
    r.render_route([MILAN, SHENZHEN], mode="plane")
    # canvas requested at 2x ...
    assert smap_cls.call_args.args[:2] == (1200, 800)
    # ... and the rendered image resized back to the target size
    assert img.resize.call_args.args[0] == (600, 400)


def test_render_route_draws_white_halo_under_main_line() -> None:
    _, line_cls, _, _ = _patched_renderer()
    r = MapRenderer(user_agent="ua")
    r.render_route([MILAN, SHENZHEN], mode="plane")
    assert line_cls.call_count == 2
    (halo_coords, halo_color, halo_width) = line_cls.call_args_list[0].args
    (main_coords, main_color, main_width) = line_cls.call_args_list[1].args
    assert halo_coords == main_coords
    assert halo_color.lower() in {"#ffffff", "white"}
    assert main_color != halo_color
    assert halo_width > main_width


def test_render_route_line_follows_geodesic_not_chord() -> None:
    _, line_cls, _, _ = _patched_renderer()
    r = MapRenderer(user_agent="ua")
    r.render_route([SHENZHEN, DUBAI], mode="plane")
    main_coords = line_cls.call_args_list[1].args[0]
    # a ~5,860 km leg must be densified into many (lon, lat) points
    assert len(main_coords) >= 13
    assert main_coords[0] == (SHENZHEN[1], SHENZHEN[0])
    assert main_coords[-1] == (DUBAI[1], DUBAI[0])


def test_render_route_marker_anchored_at_icon_center() -> None:
    _, _, icon_cls, _ = _patched_renderer()
    r = MapRenderer(user_agent="ua")
    r.render_route([MILAN], mode="truck")
    with Image.open(_MARKERS_DIR / "truck.png") as icon:
        expected = (icon.width // 2, icon.height // 2)
    assert icon_cls.call_args.args[2:] == expected


def test_default_tiles_are_english_labelled_retina() -> None:
    smap_cls, _, _, _ = _patched_renderer()
    r = MapRenderer(user_agent="ua")
    r.render_route([MILAN, SHENZHEN], mode="plane")
    kwargs = smap_cls.call_args.kwargs
    # CARTO voyager: English-first labels; @2x + tile_size 512 for crisp output
    assert "cartocdn.com" in kwargs["url_template"]
    assert "@2x" in kwargs["url_template"]
    assert kwargs["tile_size"] == 512


def test_render_supersamples_with_bumped_zoom() -> None:
    smap_cls, _, _, img = _patched_renderer()
    smap = smap_cls.return_value
    r = MapRenderer(user_agent="ua", width=600, height=400, zoom=11)
    r.render(lat=MILAN[0], lng=MILAN[1], mode="truck")
    # 2x canvas + zoom+1 keeps the same geographic extent at double resolution
    assert smap_cls.call_args.args[:2] == (1200, 800)
    assert smap.render.call_args.kwargs["zoom"] == 12
    assert img.resize.call_args.args[0] == (600, 400)
