"""HTTP requests, RabbitMQ dispatch and a real solo worker on a dedicated test queue."""

import asyncio
import os
import secrets
import time
from uuid import uuid4

import pytest
from celery.contrib.testing.worker import start_worker  # type: ignore[import-untyped]
from fastapi.testclient import TestClient
from kombu.entity import Queue
from pydantic import SecretStr
from sqlalchemy import delete

from clos.adapters.db.models import Customer, Tenant, User
from clos.adapters.db.session import make_session_factory, tenant_session
from clos.adapters.memory_runtime import memory_runtime
from clos.adapters.security.crypto import Argon2PasswordHasher
from clos.apps.api.main import app
from clos.apps.worker.main import celery_app
from clos.apps.worker.memory import dispatch_task
from clos.config import settings

URL = os.getenv("TEST_DATABASE_URL")
BROKER = os.getenv("TEST_MEMORY_BROKER_URL")
pytestmark = pytest.mark.skipif(
    not (URL and BROKER and os.getenv("TEST_MEMORY_SERVICES")),
    reason="Dedicated database and memory test broker required",
)


def test_api_to_worker_round_trip(monkeypatch: pytest.MonkeyPatch) -> None:
    assert URL and BROKER
    tenant, user, customer = uuid4(), uuid4(), uuid4()
    queue = f"memory-test-{tenant.hex}"
    password = secrets.token_urlsafe(22)
    monkeypatch.setattr(settings, "database_url", URL)
    monkeypatch.setattr(settings, "auth_jwt_secret", SecretStr(secrets.token_hex(32)))
    monkeypatch.setitem(celery_app.conf, "broker_url", BROKER)
    monkeypatch.setitem(celery_app.conf, "task_default_queue", queue)

    async def seed_or_clean(*, clean: bool) -> None:
        assert URL
        sessions = make_session_factory(URL)
        try:
            if clean:
                async with memory_runtime(sessions) as repo:
                    await repo.vectors.erase(tenant, customer)
                    await repo.cache.erase(tenant, customer)
                async with tenant_session(sessions, tenant) as db:
                    await db.execute(delete(Tenant).where(Tenant.id == tenant))
            else:
                async with sessions.begin() as db:
                    db.add(Tenant(id=tenant, slug=tenant.hex, name="test"))
                async with tenant_session(sessions, tenant) as db:
                    db.add(
                        User(
                            id=user,
                            tenant_id=tenant,
                            email="owner@example.org",
                            full_name="Test",
                            role="owner",
                            password_hash=Argon2PasswordHasher().hash(password),
                        )
                    )
                    db.add(Customer(id=customer, tenant_id=tenant, display_name="synthetic"))
        finally:
            await sessions.kw["bind"].dispose()

    def drain(client: TestClient, job_id: str) -> None:
        dispatch_task.apply_async(queue=queue)
        deadline = time.monotonic() + 45
        while time.monotonic() < deadline:
            result = client.get(f"/v1/memory/jobs/{job_id}")
            assert result.status_code == 200, result.text
            if result.json()["status"] == "completed":
                return
            time.sleep(0.25)
        pytest.fail("Memory outbox was not drained by the worker")

    # Each execution uses a unique queue, reclaimed by RabbitMQ when its consumer stops.
    test_queue = Queue(queue, routing_key=queue, auto_delete=True)  # type: ignore[no-untyped-call]
    celery_app.amqp.queues.add(test_queue)
    asyncio.run(seed_or_clean(clean=False))
    try:
        with (
            start_worker(celery_app, pool="solo", queues=[queue], perform_ping_check=False),
            TestClient(app) as client,
        ):
            login = client.post(
                "/v1/auth/token",
                json={
                    "tenant_slug": tenant.hex,
                    "email": "owner@example.org",
                    "password": password,
                },
            )
            assert login.status_code == 200, login.text
            client.headers["Authorization"] = "Bearer " + login.json()["access_token"]
            response = client.post(
                "/v1/memory/documents",
                headers={"Idempotency-Key": "upload"},
                json={
                    "source": "policy",
                    "text": "Deliver on Thursday",
                    "customer_id": str(customer),
                },
            )
            assert response.status_code == 202, response.text
            drain(client, response.json()["run_id"])
            path = f"/v1/customers/{customer}/memory"
            search = client.post(path + "/search", json={"query": "delivery"})
            assert search.status_code == 200, search.text
            assert search.json()["evidence"][0]["text"] == "Deliver on Thursday"
            assert client.get(path).json()["documents"][0]["source"] == "policy"
            erased = client.delete(path, headers={"Idempotency-Key": "erase"})
            assert erased.status_code == 202, erased.text
            drain(client, erased.json()["run_id"])
            assert client.get(path).json() == {"documents": [], "messages": []}
    finally:
        asyncio.run(seed_or_clean(clean=True))
