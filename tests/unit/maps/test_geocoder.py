from pathlib import Path

from parcel_tracker.maps.geocoder import Geocoder


def _geo() -> Geocoder:
    ds = Path(__file__).resolve().parents[2] / "fixtures" / "maps" / "cities_tiny.tsv"
    return Geocoder(dataset_path=ds)


def test_geocode_primary_english_name() -> None:
    result = _geo().geocode("Milan, IT")
    assert result is not None
    assert round(result[0], 2) == 45.46


def test_geocode_local_alternate_name() -> None:
    # "Milano" is an alternate name, not the GeoNames primary "Milan"
    result = _geo().geocode("Milano, IT")
    assert result is not None
    assert round(result[0], 2) == 45.46


def test_geocode_alternate_without_country() -> None:
    assert _geo().geocode("Roma") is not None


def test_geocode_unknown_returns_none() -> None:
    assert _geo().geocode("Atlantis, XX") is None


def test_geocode_none_input() -> None:
    assert _geo().geocode(None) is None
