"""Placeholder worker process; queue integration arrives in a later phase."""

import time

import structlog

from clos.config import settings
from clos.logging import configure_logging

configure_logging(settings.log_level)
logger = structlog.get_logger(__name__)


def main() -> None:
    """Keep the worker container alive until task consumers are implemented."""
    logger.info("worker_started", component="worker")
    while True:
        time.sleep(60)


if __name__ == "__main__":
    main()

