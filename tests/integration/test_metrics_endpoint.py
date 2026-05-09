"""Integration test: metrics exporter lifecycle wired through Config."""

from __future__ import annotations

import socket
import urllib.request

from parcel_tracker.observability.exporter import ExporterConfig, start_metrics_exporter


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def test_metrics_endpoint_serves_default_metrics() -> None:
    cfg = ExporterConfig(enabled=True, host="127.0.0.1", port=_free_port())
    assert start_metrics_exporter(cfg) is True

    url = f"http://{cfg.host}:{cfg.port}/metrics"
    with urllib.request.urlopen(url, timeout=2) as response:  # noqa: S310 (test)
        body = response.read().decode("utf-8")
    assert response.status == 200
    assert "parceltracker_check_total" in body
