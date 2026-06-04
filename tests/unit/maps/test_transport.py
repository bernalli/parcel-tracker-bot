from parcel_tracker.maps.transport import infer_transport_mode


def test_air() -> None:
    assert infer_transport_mode("Lufthansa", "Departed from airport on flight LH123") == "plane"


def test_ship() -> None:
    assert infer_transport_mode(None, "Loaded on vessel at port of Genova") == "ship"


def test_out_for_delivery_truck() -> None:
    assert infer_transport_mode("BRT", "Out for delivery") == "truck"


def test_default_parcel() -> None:
    assert infer_transport_mode(None, "Information received") == "parcel"


def test_handles_none() -> None:
    assert infer_transport_mode(None, None) == "parcel"
