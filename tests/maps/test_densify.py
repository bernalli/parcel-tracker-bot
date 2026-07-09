from __future__ import annotations

from parcel_tracker.maps.renderer import _densify

SHENZHEN = (22.5431, 114.0579)
DUBAI = (25.2532, 55.3657)
MILAN = (45.4642, 9.1900)
TURIN = (45.0703, 7.6869)  # ~125 km from Milan


def test_densify_long_leg_inserts_intermediate_points() -> None:
    pts = _densify([SHENZHEN, DUBAI], max_km=500.0)
    assert pts[0] == SHENZHEN
    assert pts[-1] == DUBAI
    # ~5,860 km leg at 500 km spacing -> at least 12 segments
    assert len(pts) >= 13


def test_densify_follows_great_circle_not_straight_lerp() -> None:
    pts = _densify([SHENZHEN, DUBAI], max_km=500.0)
    mid_lat = pts[len(pts) // 2][0]
    # linear interpolation would give ~23.9; the great-circle arc bows north
    assert mid_lat > 24.5


def test_densify_short_leg_unchanged() -> None:
    assert _densify([MILAN, TURIN], max_km=500.0) == [MILAN, TURIN]


def test_densify_single_point_unchanged() -> None:
    assert _densify([MILAN], max_km=500.0) == [MILAN]


def test_densify_multi_leg_only_expands_long_segments() -> None:
    pts = _densify([SHENZHEN, DUBAI, MILAN, TURIN], max_km=500.0)
    # both long legs expanded, the Milan-Turin tail kept as-is
    assert pts[-2:] == [MILAN, TURIN]
    assert len(pts) > 20
