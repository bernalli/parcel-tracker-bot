"""structlog setup: intercept stdlib logging, output JSON in prod / console in dev."""

from __future__ import annotations

import hashlib
import logging
import os
import sys
from typing import Any

import structlog
from structlog.types import Processor

# Standard kwargs accepted by `logging.Logger._log` — anything else is shuttled
# into the `extra` dict by the patched `_log` below.
_STDLIB_LOG_KWARGS = frozenset({"exc_info", "extra", "stack_info", "stacklevel"})

_original_log = logging.Logger._log


def _log_with_kwargs(
    self: logging.Logger,
    level: int,
    msg: object,
    args: tuple[Any, ...],
    **kwargs: Any,
) -> None:
    """Wrap stdlib `Logger._log` to forward unknown kwargs via the `extra` dict.

    This makes `logger.info("event", tracker="dhl")` work on stdlib loggers, so the
    extra fields are surfaced by the structlog `ExtraAdder` processor in the
    foreign-pre-chain. Stdlib-native kwargs (`exc_info`, `extra`, `stack_info`,
    `stacklevel`) are passed through unchanged.
    """
    extra = dict(kwargs.pop("extra", None) or {})
    for key in list(kwargs):
        if key not in _STDLIB_LOG_KWARGS:
            extra[key] = kwargs.pop(key)
    if extra:
        kwargs["extra"] = extra
    _original_log(self, level, msg, args, **kwargs)


def configure_logging(*, log_level: str = "INFO", log_format: str = "json") -> None:
    """
    Configure structlog to intercept stdlib logging.

    Args:
        log_level: Standard log level name (DEBUG/INFO/WARNING/ERROR).
        log_format: 'json' for Docker/production or 'console' for dev (colored if TTY).
    """
    # Patch stdlib Logger so foreign callers can pass kwargs (forwarded as `extra`).
    logging.Logger._log = _log_with_kwargs  # type: ignore[assignment,method-assign]

    timestamper = structlog.processors.TimeStamper(fmt="iso", utc=True)

    shared_processors: list[Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.ExtraAdder(),
        timestamper,
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
    ]

    renderer: Processor
    if log_format == "json":
        renderer = structlog.processors.JSONRenderer()
    else:
        renderer = structlog.dev.ConsoleRenderer(colors=sys.stderr.isatty())

    structlog.configure(
        processors=[
            *shared_processors,
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        wrapper_class=structlog.stdlib.BoundLogger,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )

    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(
        structlog.stdlib.ProcessorFormatter(
            foreign_pre_chain=shared_processors,
            processors=[
                structlog.stdlib.ProcessorFormatter.remove_processors_meta,
                renderer,
            ],
        )
    )

    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(getattr(logging, log_level.upper()))

    logging.getLogger("httpx").setLevel(logging.WARNING)


def hash_tracking_id(tracking_id: str) -> str:
    """Hash a tracking ID for privacy in structured logs.

    Returns SHA-256 truncated to 12 hex chars by default.
    Returns the raw tracking_id if env LOG_FULL_TRACKING_ID is 'true'.
    """
    if os.getenv("LOG_FULL_TRACKING_ID", "false").lower() == "true":
        return tracking_id
    return hashlib.sha256(tracking_id.encode("utf-8")).hexdigest()[:12]
