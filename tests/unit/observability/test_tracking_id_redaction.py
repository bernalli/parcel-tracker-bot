from __future__ import annotations

import io
import logging

import pytest

from parcel_tracker.observability import logging as obs

CODE = "JD014600006281230704"


@pytest.fixture
def capture(monkeypatch: pytest.MonkeyPatch) -> io.StringIO:
    buf = io.StringIO()
    monkeypatch.setattr(obs.sys, "stderr", buf)
    obs.configure_logging(log_level="DEBUG", log_format="json")
    return buf


def test_codes_are_hashed_everywhere(capture: io.StringIO, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LOG_FULL_TRACKING_ID", "false")
    log = logging.getLogger("parcel_tracker.test")
    log.warning("Tracker %s failed for %s", "dhl", CODE)
    log.warning("fetch failed", extra={"tracking_id": CODE})
    try:
        raise RuntimeError(f"404 for url 'https://x.invalid/track?id={CODE}'")
    except RuntimeError:
        log.exception("boom")
    out = capture.getvalue()
    assert CODE not in out
    assert obs.hash_tracking_id(CODE) in out
    assert "RuntimeError" in out  # traceback kept


def test_opt_out_keeps_raw_codes(capture: io.StringIO, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LOG_FULL_TRACKING_ID", "true")
    logging.getLogger("parcel_tracker.test").warning("code %s", CODE)
    assert CODE in capture.getvalue()


def test_ordinary_words_untouched(capture: io.StringIO, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LOG_FULL_TRACKING_ID", "false")
    logging.getLogger("parcel_tracker.test").warning("HTTP 503 from DHL after 30s")
    assert "HTTP 503 from DHL after 30s" in capture.getvalue()
