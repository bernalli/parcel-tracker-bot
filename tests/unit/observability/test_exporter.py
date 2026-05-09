"""Tests for Prometheus exporter lifecycle."""

from __future__ import annotations

import socket
import urllib.request

import pytest

from parcel_tracker.observability.exporter import (
    ExporterConfig,
    start_metrics_exporter,
)


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def test_start_metrics_exporter_disabled_returns_false() -> None:
    cfg = ExporterConfig(enabled=False, host="127.0.0.1", port=_free_port())
    started = start_metrics_exporter(cfg)
    assert started is False


def test_start_metrics_exporter_serves_metrics_endpoint() -> None:
    cfg = ExporterConfig(enabled=True, host="127.0.0.1", port=_free_port())
    started = start_metrics_exporter(cfg)
    assert started is True

    url = f"http://{cfg.host}:{cfg.port}/metrics"
    with urllib.request.urlopen(url, timeout=2) as response:  # noqa: S310 (test)
        body = response.read().decode("utf-8")
    assert response.status == 200
    assert "parceltracker_check_total" in body


def test_start_metrics_exporter_handles_bind_failure_gracefully(
    caplog: pytest.LogCaptureFixture,
) -> None:
    # Bind a port first to force conflict.
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.bind(("127.0.0.1", 0))
    sock.listen(1)
    used_port = sock.getsockname()[1]
    try:
        cfg = ExporterConfig(enabled=True, host="127.0.0.1", port=used_port)
        started = start_metrics_exporter(cfg)
        assert started is False
    finally:
        sock.close()
