"""Structured JSON logging configuration."""

import logging

import structlog


def configure_logging(log_level: str) -> None:
    """Configure stdlib and structlog to emit JSON records."""
    resolved_level = logging.getLevelName(log_level.upper())
    logging.basicConfig(level=resolved_level, format="%(message)s")
    logging.getLogger().setLevel(resolved_level)
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(resolved_level),
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )
