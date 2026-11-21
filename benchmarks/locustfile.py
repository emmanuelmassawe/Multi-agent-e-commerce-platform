"""Synthetic authenticated run admission workload. Invoked by run_api_load.py."""

import os
from uuid import uuid4

from locust import HttpUser, task  # type: ignore[import-not-found]


class Merchant(HttpUser):  # type: ignore[misc]
    @task  # type: ignore[untyped-decorator]
    def submit(self) -> None:
        with self.client.post(
            "/v1/runs",
            headers={
                "Authorization": "Bearer " + os.environ["CLOS_BENCH_TOKEN"],
                "Idempotency-Key": str(uuid4()),
            },
            json={"message": "Check synthetic inventory"},
            catch_response=True,
        ) as response:
            if response.status_code != 202 or not response.json().get("run_id"):
                response.failure(f"Expected accepted run, received {response.status_code}")
