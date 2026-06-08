"""A failing per-parcel task must be logged, not silently swallowed by the
``asyncio.gather(return_exceptions=True)`` batch (and must not abort the batch).
"""

from __future__ import annotations

import logging

from parcel_tracker.core.scheduler import _log_batch_errors
from parcel_tracker.db.models import Parcel, ShipmentStatus


def _parcel(tn: str) -> Parcel:
    return Parcel(tracking_number=tn, user_id=7, status=ShipmentStatus.IN_TRANSIT)


def test_logs_exception_results(caplog) -> None:  # type: ignore[no-untyped-def]
    batch = [(7, _parcel("TN_OK")), (7, _parcel("TN_BAD"))]
    results = ["updated", RuntimeError("boom")]
    with caplog.at_level(logging.WARNING):
        _log_batch_errors(batch, results)
    assert "TN_BAD" in caplog.text
    assert "boom" in caplog.text
    assert "TN_OK" not in caplog.text


def test_no_log_when_all_ok(caplog) -> None:  # type: ignore[no-untyped-def]
    batch = [(7, _parcel("TN1")), (7, _parcel("TN2"))]
    with caplog.at_level(logging.WARNING):
        _log_batch_errors(batch, ["updated", "no_change"])
    assert caplog.records == []
