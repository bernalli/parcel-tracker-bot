"""Tests for structlog hybrid setup."""

from __future__ import annotations

import json
import logging
from collections.abc import Iterator

import pytest
import structlog

from parcel_tracker.observability.logging import configure_logging, hash_tracking_id


@pytest.fixture(autouse=True)
def _reset_structlog() -> Iterator[None]:
    """Reset structlog config between tests to avoid global state leakage."""
    structlog.reset_defaults()
    yield
    structlog.reset_defaults()


def test_configure_logging_json_format_emits_json(capsys: pytest.CaptureFixture[str]) -> None:
    configure_logging(log_level="INFO", log_format="json")
    logger = logging.getLogger("test_module")

    logger.info("event", tracker="dhl")  # pyright: ignore[reportCallIssue]

    captured = capsys.readouterr()
    assert captured.err.strip(), "expected log line on stderr"
    parsed = json.loads(captured.err.strip().splitlines()[-1])
    assert parsed["event"] == "event"
    assert parsed["tracker"] == "dhl"
    assert parsed["level"] == "info"
    assert "timestamp" in parsed


def test_configure_logging_console_format_does_not_emit_json(
    capsys: pytest.CaptureFixture[str],
) -> None:
    configure_logging(log_level="INFO", log_format="console")
    logger = logging.getLogger("test_module")

    logger.info("event happened")

    captured = capsys.readouterr()
    assert "event happened" in captured.err
    # Console renderer is human-readable, not JSON.
    with pytest.raises(json.JSONDecodeError):
        json.loads(captured.err.strip().splitlines()[-1])


def test_configure_logging_respects_log_level(capsys: pytest.CaptureFixture[str]) -> None:
    configure_logging(log_level="WARNING", log_format="json")
    logger = logging.getLogger("test_module")

    logger.info("ignored")
    logger.warning("kept")

    captured = capsys.readouterr()
    lines = [line for line in captured.err.strip().splitlines() if line.strip()]
    assert len(lines) == 1
    parsed = json.loads(lines[0])
    assert parsed["event"] == "kept"


def test_hash_tracking_id_default_hashes() -> None:
    h = hash_tracking_id("ABC1234567890")
    assert h != "ABC1234567890"
    assert len(h) == 12
    assert all(c in "0123456789abcdef" for c in h)


def test_hash_tracking_id_passthrough_when_full_enabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("LOG_FULL_TRACKING_ID", "true")
    assert hash_tracking_id("ABC1234567890") == "ABC1234567890"


def test_hash_tracking_id_deterministic() -> None:
    a = hash_tracking_id("XYZ")
    b = hash_tracking_id("XYZ")
    assert a == b
