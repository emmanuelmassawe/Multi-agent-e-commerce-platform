"""PostgreSQL checkpoint recovery test (set CHECKPOINT_DATABASE_URL to enable)."""

import os
import subprocess
import sys
import time
from pathlib import Path
from uuid import uuid4

import pytest

CHECKPOINT_DATABASE_URL = os.environ.get("CHECKPOINT_DATABASE_URL")
pytestmark = pytest.mark.skipif(
    CHECKPOINT_DATABASE_URL is None,
    reason="CHECKPOINT_DATABASE_URL is not configured",
)


def test_graph_resumes_after_worker_process_is_killed() -> None:
    assert CHECKPOINT_DATABASE_URL is not None
    tenant_id, run_id = uuid4(), uuid4()
    marker = Path.cwd() / f".checkpoint-ready-{run_id.hex}"
    probe = os.path.join(os.path.dirname(__file__), "checkpoint_worker_probe.py")
    environment = os.environ.copy()
    worker = subprocess.Popen(
        [sys.executable, probe, "pause", str(tenant_id), str(run_id), str(marker)],
        env=environment,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    # This outer bound includes interpreter startup and imports under coverage.
    # The probe independently bounds database and graph work to 30 seconds.
    deadline = time.monotonic() + 90
    try:
        while not marker.exists() and worker.poll() is None and time.monotonic() < deadline:
            time.sleep(0.05)
        if worker.poll() is not None:
            pytest.fail(f"Worker exited before termination: {worker.communicate()[1]}")
        assert marker.exists(), "worker did not persist its pause checkpoint"
        worker.terminate()
        worker.wait(timeout=10)
        resumed = subprocess.run(
            [sys.executable, probe, "resume", str(tenant_id), str(run_id), str(marker)],
            env=environment,
            capture_output=True,
            text=True,
            check=True,
            timeout=90,
        )
        assert "completed" in resumed.stdout
        assert "inventory" in resumed.stdout and "pricing" in resumed.stdout
    finally:
        if worker.poll() is None:
            worker.terminate()
            worker.wait(timeout=10)
        marker.unlink(missing_ok=True)
