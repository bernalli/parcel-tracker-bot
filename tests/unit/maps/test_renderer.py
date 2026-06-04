from unittest.mock import MagicMock, patch

from PIL import Image

from parcel_tracker.maps.renderer import MapRenderer


def test_render_returns_png_bytes() -> None:
    renderer = MapRenderer(user_agent="parcel-tracker-bot/0.2 (self-hosted)")
    fake_img = Image.new("RGB", (16, 16), (255, 255, 255))
    with patch("parcel_tracker.maps.renderer.StaticMap") as sm_cls:
        sm = MagicMock()
        sm.render.return_value = fake_img
        sm_cls.return_value = sm
        png = renderer.render(lat=45.46, lng=9.19, mode="truck")
    assert png[:8] == b"\x89PNG\r\n\x1a\n"  # PNG magic header
    sm.add_marker.assert_called_once()


def test_unknown_mode_falls_back_to_parcel() -> None:
    renderer = MapRenderer(user_agent="x")
    fake_img = Image.new("RGB", (16, 16), (255, 255, 255))
    with patch("parcel_tracker.maps.renderer.StaticMap") as sm_cls:
        sm = MagicMock()
        sm.render.return_value = fake_img
        sm_cls.return_value = sm
        png = renderer.render(lat=0.0, lng=0.0, mode="banana")  # invalid → parcel marker
    assert png[:8] == b"\x89PNG\r\n\x1a\n"
