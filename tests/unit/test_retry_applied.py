"""The retry policy is applied to tracker HTTP calls and the scheduler tells a
transient failure apart from a genuine "not found" (#19)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from email.utils import format_datetime

import httpx
import pytest
import respx

from parcel_tracker.core import retry_policy
from parcel_tracker.core.http_client import HttpClient
from parcel_tracker.core.retry_policy import (
    MAX_RETRY_AFTER_SECONDS,
    RetryProfile,
    retry_after_seconds,
    send_with_retry,
)
from parcel_tracker.core.scheduler import check_updates
from parcel_tracker.core.tracker_base import (
    FetchError,
    TrackingResult,
    classify_exception,
    classify_status,
)
from parcel_tracker.trackers.ups import UpsTracker
from tests.unit.test_scheduler_fallback import (
    _make_context,
    _make_parcel,
    _make_tracker_mock,
    _success_result,
)

_URL = "https://example.test/x"


@pytest.fixture
def sleeps(monkeypatch: pytest.MonkeyPatch) -> list[float]:
    recorded: list[float] = []

    async def _record(seconds: float) -> None:
        recorded.append(seconds)

    monkeypatch.setattr(retry_policy, "_sleep", _record)
    return recorded


def _response(status: int, headers: dict[str, str] | None = None) -> httpx.Response:
    return httpx.Response(status, headers=headers, request=httpx.Request("GET", _URL))


@pytest.mark.asyncio
async def test_transient_status_is_retried_until_success(sleeps: list[float]) -> None:
    responses = iter([_response(503), _response(502), _response(200)])

    async def send() -> httpx.Response:
        return next(responses)

    result = await send_with_retry(send, RetryProfile.HTTP_DEFAULT)
    assert result.status_code == 200
    assert len(sleeps) == 2
    assert all(0 < s <= RetryProfile.HTTP_DEFAULT.max_wait_seconds for s in sleeps)


@pytest.mark.asyncio
async def test_retry_after_header_sets_the_wait(sleeps: list[float]) -> None:
    responses = iter([_response(429, {"Retry-After": "7"}), _response(200)])

    async def send() -> httpx.Response:
        return next(responses)

    await send_with_retry(send, RetryProfile.HTTP_DEFAULT)
    assert sleeps == [7.0]


@pytest.mark.asyncio
async def test_exhausted_retries_return_last_response(sleeps: list[float]) -> None:
    calls = 0

    async def send() -> httpx.Response:
        nonlocal calls
        calls += 1
        return _response(503)

    result = await send_with_retry(send, RetryProfile.HTTP_DEFAULT)
    assert result.status_code == 503
    assert calls == RetryProfile.HTTP_DEFAULT.max_attempts


@pytest.mark.asyncio
async def test_network_error_is_retried_then_reraised(sleeps: list[float]) -> None:
    calls = 0

    async def send() -> httpx.Response:
        nonlocal calls
        calls += 1
        raise httpx.ConnectTimeout("slow")

    with pytest.raises(httpx.ConnectTimeout):
        await send_with_retry(send, RetryProfile.HTTP_DEFAULT)
    assert calls == RetryProfile.HTTP_DEFAULT.max_attempts


@pytest.mark.asyncio
async def test_non_transient_status_is_not_retried(sleeps: list[float]) -> None:
    calls = 0

    async def send() -> httpx.Response:
        nonlocal calls
        calls += 1
        return _response(404)

    assert (await send_with_retry(send, RetryProfile.HTTP_DEFAULT)).status_code == 404
    assert calls == 1
    assert sleeps == []


def test_retry_after_http_date_and_cap() -> None:
    now = datetime(2026, 6, 4, 12, 0, tzinfo=UTC)
    soon = format_datetime(now + timedelta(seconds=12), usegmt=True)
    assert retry_after_seconds(_response(503, {"Retry-After": soon}), now=now) == 12.0
    assert retry_after_seconds(_response(503, {"Retry-After": "3600"})) == MAX_RETRY_AFTER_SECONDS
    assert retry_after_seconds(_response(503, {"Retry-After": "soon"})) is None
    assert retry_after_seconds(_response(503)) is None


def test_classification() -> None:
    assert classify_status(429) is FetchError.RATE_LIMITED
    assert classify_status(503) is FetchError.TRANSIENT
    assert classify_status(408) is FetchError.TRANSIENT
    assert classify_status(404) is FetchError.NOT_FOUND
    assert classify_status(403) is FetchError.PERMANENT
    assert classify_exception(httpx.ReadTimeout("t")) is FetchError.TRANSIENT
    assert classify_exception(ValueError("bad")) is FetchError.PERMANENT


@pytest.mark.asyncio
async def test_tracker_recovers_from_a_momentary_outage(sleeps: list[float]) -> None:
    html = (
        "<div class='activity-row'><span class='activity-date'>01/06/2026</span>"
        "<span class='activity-location'>Milano</span>"
        "<span class='activity-description'>In Transit</span></div>"
    )
    tracker = UpsTracker(http_client=HttpClient(timeout=5.0))
    with respx.mock(assert_all_called=False) as mock:
        mock.get(UpsTracker.TRACK_URL).mock(
            side_effect=[httpx.Response(503), httpx.Response(200, text=html)]
        )
        result = await tracker.fetch("1Z999AA10123456784")
    assert result.found
    assert len(sleeps) == 1


@pytest.mark.asyncio
async def test_tracker_reports_the_kind_of_failure(sleeps: list[float]) -> None:
    tracker = UpsTracker(http_client=HttpClient(timeout=5.0))
    with respx.mock(assert_all_called=False) as mock:
        mock.get(UpsTracker.TRACK_URL).respond(429)
        result = await tracker.fetch("1Z999AA10123456784")
    assert not result.found
    assert result.error_kind is FetchError.RATE_LIMITED


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("kind", "records_failure"),
    [(FetchError.TRANSIENT, True), (FetchError.RATE_LIMITED, False)],
)
async def test_transient_failure_does_not_burn_the_fallback(
    kind: FetchError, records_failure: bool
) -> None:
    parcel = _make_parcel()
    primary = _make_tracker_mock(
        "primary",
        fetch_result=TrackingResult(
            tracking_number=parcel.tracking_number, found=False, error="x", error_kind=kind
        ),
    )
    fallback = _make_tracker_mock("fallback", fetch_result=_success_result())
    ctx = _make_context([primary, fallback], parcel)

    await check_updates(ctx)

    fallback.fetch.assert_not_awaited()
    health = ctx.bot_data["health"]
    assert health.record_failure.await_count == (1 if records_failure else 0)


@pytest.mark.asyncio
async def test_not_found_still_falls_through() -> None:
    parcel = _make_parcel()
    primary = _make_tracker_mock(
        "primary",
        fetch_result=TrackingResult(tracking_number=parcel.tracking_number, found=False),
    )
    fallback = _make_tracker_mock("fallback", fetch_result=_success_result())
    ctx = _make_context([primary, fallback], parcel)

    await check_updates(ctx)

    fallback.fetch.assert_awaited_once()
