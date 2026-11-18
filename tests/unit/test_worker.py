"""Worker entry point and delivery safety configuration smoke tests."""

import pytest

from clos.apps.worker import main as worker


def test_worker_starts_celery_consumer(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: list[list[str]] = []

    def fake_worker_main(arguments: list[str]) -> None:
        captured.append(arguments)

    monkeypatch.setattr(worker.celery_app, "worker_main", fake_worker_main)
    worker.main()
    assert captured == [["worker", "--loglevel=INFO"]]


def test_worker_enables_late_ack_and_rejects_lost_worker_tasks() -> None:
    assert worker.celery_app.conf.task_acks_late is True
    assert worker.celery_app.conf.task_reject_on_worker_lost is True
    assert worker.celery_app.conf.worker_prefetch_multiplier == 1
