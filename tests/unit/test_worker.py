"""Worker entry point smoke test."""

import pytest

from clos.apps.worker import main as worker


def test_worker_starts_and_logs() -> None:
    def stop(_: float) -> None:
        raise KeyboardInterrupt

    with pytest.raises(KeyboardInterrupt):
        worker.main(sleep=stop)
