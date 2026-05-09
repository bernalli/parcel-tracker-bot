"""Prometheus HTTP exporter lifecycle: start_http_server with graceful failure."""

from __future__ import annotations

import logging
from dataclasses import dataclass

from prometheus_client import start_http_server

# Importing the metrics module registers all collectors on the default
# Prometheus registry as a side effect, so that start_http_server() exposes them.
from parcel_tracker.observability import metrics as _metrics  # noqa: F401

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class ExporterConfig:
    """Config for the Prometheus exporter HTTP server."""

    enabled: bool
    host: str
    port: int


def start_metrics_exporter(config: ExporterConfig) -> bool:
    """Start the Prometheus exporter HTTP server.

    Returns True on successful start, False if disabled or on bind failure.
    Failures are logged at ERROR but never raised — bot continues without metrics
    (graceful degradation).
    """
    if not config.enabled:
        logger.info("observability.metrics.disabled")
        return False

    try:
        start_http_server(config.port, addr=config.host)
    except OSError as exc:
        logger.error(
            "observability.metrics.start_failed",
            extra={
                "error_class": type(exc).__name__,
                "error_message": str(exc),
                "host": config.host,
                "port": config.port,
            },
        )
        return False

    logger.info(
        "observability.metrics.started",
        extra={"host": config.host, "port": config.port},
    )
    return True
