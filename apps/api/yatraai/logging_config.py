"""Structured logging with request-id correlation.

Console-friendly in development, JSON in production. Every log line emitted
inside a request carries ``request_id`` so traces can be stitched together.
"""

from __future__ import annotations

import logging
import sys
from contextvars import ContextVar

import structlog

request_id_ctx: ContextVar[str | None] = ContextVar("request_id", default=None)
user_id_ctx: ContextVar[str | None] = ContextVar("user_id", default=None)

_CONFIGURED = False


def _inject_context(_logger, _name, event_dict):
    rid = request_id_ctx.get()
    if rid:
        event_dict.setdefault("request_id", rid)
    uid = user_id_ctx.get()
    if uid:
        event_dict.setdefault("user_id", uid)
    return event_dict


def configure_logging(level: str = "INFO", json_output: bool = False) -> None:
    global _CONFIGURED
    if _CONFIGURED:
        return

    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=getattr(logging, level.upper(), logging.INFO),
    )
    # Uvicorn access logs are replaced by our own request middleware.
    logging.getLogger("uvicorn.access").handlers = []
    logging.getLogger("uvicorn.access").propagate = False

    processors: list = [
        structlog.contextvars.merge_contextvars,
        _inject_context,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
    ]
    processors.append(
        structlog.processors.JSONRenderer()
        if json_output
        else structlog.dev.ConsoleRenderer(colors=False)
    )

    structlog.configure(
        processors=processors,
        wrapper_class=structlog.make_filtering_bound_logger(
            getattr(logging, level.upper(), logging.INFO)
        ),
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )
    _CONFIGURED = True


def get_logger(name: str = "yatraai") -> structlog.stdlib.BoundLogger:
    if not _CONFIGURED:
        configure_logging()
    return structlog.get_logger(name)
