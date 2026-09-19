"""Structured logging configuration."""

import logging
import sys

import structlog

from dealerai_ops.core.config import LogLevel
from dealerai_ops.core.redaction import redact_structlog_event


def configure_logging(log_level: LogLevel = "INFO") -> None:
    """Configure stdlib logging and structlog for JSON logs."""
    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=log_level,
        force=True,
    )

    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            redact_structlog_event,
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(
            logging.getLevelName(log_level),
        ),
        logger_factory=structlog.PrintLoggerFactory(file=sys.stdout),
        cache_logger_on_first_use=True,
    )
