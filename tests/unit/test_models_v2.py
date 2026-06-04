from parcel_tracker.core.tracker_base import TrackingResult
from parcel_tracker.db.models import Parcel


def test_parcel_has_v2_fields() -> None:
    p = Parcel(tracking_number="X", user_id=1)
    assert p.last_location is None
    assert p.transport_mode is None
    assert p.delivery_disputed is False


def test_tracking_result_has_last_location() -> None:
    r = TrackingResult(tracking_number="X", found=True)
    assert r.last_location is None
