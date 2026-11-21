"""Celery worker entry point for resumable agent runs."""

from celery import Celery  # type: ignore[import-untyped]

from clos.config import settings
from clos.logging import configure_logging

configure_logging(settings.log_level)

celery_app = Celery(
    "clos",
    broker=settings.rabbitmq_url,
    include=["clos.apps.worker.tasks", "clos.apps.worker.memory", "clos.apps.worker.delivery"],
)
celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    worker_prefetch_multiplier=1,
    broker_connection_retry_on_startup=True,
    task_default_queue="agent-runs",
    beat_schedule={
        "dispatch-memory": {"task": "clos.dispatch_memory", "schedule": 15.0},
        "dispatch-delivery": {"task": "clos.dispatch_delivery", "schedule": 2.0},
    },
)


def main() -> None:
    """Start a RabbitMQ-backed Celery worker."""
    celery_app.worker_main(["worker", "--loglevel=INFO"])


if __name__ == "__main__":
    main()
