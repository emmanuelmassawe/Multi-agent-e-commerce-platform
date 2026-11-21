"""Phase 6 delivery against PostgreSQL, Redis and a RabbitMQ-backed Celery worker."""

import asyncio
import base64
import hmac
import json
import os
import secrets
import time
from collections.abc import AsyncIterator, Iterator
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from decimal import Decimal
from unittest.mock import Mock
from uuid import UUID, uuid4

import pytest
from celery.contrib.testing.worker import start_worker  # type: ignore[import-untyped]
from fastapi.testclient import TestClient
from kombu.entity import Queue
from pydantic import SecretStr
from redis.asyncio import Redis
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from clos.adapters.db.models import (
    AsyncJob,
    AuditLog,
    CompetitorListing,
    Order,
    Product,
    Shipment,
    ShipmentEvent,
    Tenant,
    ToolCall,
    User,
)
from clos.adapters.db.session import make_session_factory, tenant_session
from clos.adapters.security.crypto import JwtTokenIssuer
from clos.application.delivery import signature
from clos.apps.api.main import app
from clos.apps.worker.delivery import consume, dispatch_delivery, tick
from clos.apps.worker.main import celery_app
from clos.config import IntegrationBinding, settings
from clos.domain.identity import Role

URL = os.environ.get("TEST_DATABASE_URL", "")
BROKER = os.environ.get("TEST_MEMORY_BROKER_URL", "")
pytestmark = pytest.mark.skipif(
    not (URL and BROKER and os.getenv("TEST_MEMORY_SERVICES")),
    reason="Dedicated PostgreSQL, Redis and RabbitMQ required",
)


@asynccontextmanager
async def scoped(tenant: UUID) -> AsyncIterator[AsyncSession]:
    sessions = make_session_factory(URL)
    try:
        async with tenant_session(sessions, tenant) as db:
            yield db
    finally:
        await sessions.kw["bind"].dispose()


@pytest.fixture
def merchant(monkeypatch: pytest.MonkeyPatch) -> Iterator[tuple[TestClient, UUID, str]]:
    tenant, user = uuid4(), uuid4()
    secret = secrets.token_hex(32)
    monkeypatch.setattr(settings, "database_url", URL)
    monkeypatch.setattr(settings, "auth_jwt_secret", SecretStr(secret))
    monkeypatch.setattr(settings, "app_env", "test")
    monkeypatch.setattr(settings, "gemini_api_key", None)
    monkeypatch.setattr(settings, "gemini_fallback_api_keys", None)
    monkeypatch.setattr(settings, "delivery_max_attempts", 1)

    async def seed() -> None:
        async with scoped(tenant) as db:
            db.add(Tenant(id=tenant, slug=tenant.hex, name="Synthetic delivery tenant"))
            await db.flush()
            db.add(
                User(
                    id=user,
                    tenant_id=tenant,
                    email="owner@example.org",
                    full_name="Test",
                    role="owner",
                    password_hash="unused",
                )
            )

    async def cleanup() -> None:
        async with scoped(tenant) as db:
            await db.execute(delete(Tenant).where(Tenant.id == tenant))

    asyncio.run(seed())
    try:
        with TestClient(app) as client:
            jwt = JwtTokenIssuer(secret).create_access_token(
                user_id=user, tenant_id=tenant, role=Role.OWNER, expires_in_seconds=300
            )
            client.headers["Authorization"] = f"Bearer {jwt}"
            yield client, tenant, jwt
    finally:
        asyncio.run(cleanup())


def test_run_through_broker(
    merchant: tuple[TestClient, UUID, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    client, tenant, jwt = merchant
    queue = "delivery-test-" + tenant.hex
    monkeypatch.setitem(celery_app.conf, "broker_url", BROKER)
    monkeypatch.setitem(celery_app.conf, "task_default_queue", queue)
    celery_app.amqp.queues.add(Queue(queue, routing_key=queue, auto_delete=True))  # type: ignore[no-untyped-call]
    headers = {"Idempotency-Key": "same-request"}

    def submit() -> str:
        response = client.post(
            "/v1/runs", json={"message": "check inventory stock"}, headers=headers
        )
        assert response.status_code == 202, response.text
        assert response.headers["Location"].endswith(response.json()["run_id"])
        return str(response.json()["run_id"])

    with ThreadPoolExecutor(max_workers=2) as pool:
        first, duplicate = list(pool.map(lambda _: submit(), range(2)))
    assert duplicate == first
    assert (
        client.post("/v1/runs", json={"message": "different"}, headers=headers).status_code == 409
    )
    path = "/v1/runs/" + first
    with start_worker(celery_app, pool="solo", queues=[queue], perform_ping_check=False):
        dispatch_delivery.apply_async(queue=queue)
        deadline = time.monotonic() + 45
        state = ""
        while time.monotonic() < deadline:
            status = client.get(path)
            assert status.status_code == 200, status.text
            state = status.json()["status"]
            if state in {"completed", "failed", "budget_exceeded"}:
                break
            time.sleep(1)
        assert state == "completed", client.get("/v1/dead-letters").json()
    response = client.get(path + "/events")
    assert response.status_code == 200
    rows = [
        json.loads(line[6:]) for line in response.text.splitlines() if line.startswith("data: ")
    ]
    types = [r["event_type"] for r in rows]
    assert types[0] == "run_queued" and types[-1] == "run_finished"
    assert {"node_started", "tool_started", "tool_finished", "token_usage"} <= set(types)
    assert types.count("tool_started") == 1
    assert (
        client.get(path + "/events", headers={"Last-Event-ID": rows[-2]["event_id"]}).text.count(
            "data: "
        )
        == 1
    )
    assert client.get(path + "/events", headers={"Last-Event-ID": str(uuid4())}).status_code == 404

    async def isolate() -> None:
        async with scoped(tenant) as db:
            assert await db.scalar(select(func.count()).select_from(ToolCall)) == 1
        async with scoped(uuid4()) as db:
            assert await db.get(AsyncJob, UUID(first)) is None

    asyncio.run(isolate())
    approval = uuid4()

    async def notify() -> None:
        async with scoped(tenant) as db:
            db.add(
                AuditLog(
                    tenant_id=tenant,
                    action="approval_requested",
                    entity_type="approval_request",
                    entity_id=approval,
                    details={"run_id": first, "tool": "order", "status": "pending"},
                )
            )

    asyncio.run(notify())
    with client.websocket_connect(
        "/v1/approvals/ws", headers={"Authorization": "Bearer " + jwt}
    ) as ws:
        notice = ws.receive_json()
        assert notice["event_type"] == "approval_requested" and notice["approval_id"] == str(
            approval
        )
        assert ws.receive_json() == {"type": "heartbeat"}


class RecordingTransport:
    def __init__(self) -> None:
        self.sent: list[tuple[bytes, dict[str, str]]] = []

    async def send(self, url: str, data: bytes, headers: dict[str, str]) -> None:
        self.sent.append((data, headers))

    async def feed(self, url: str, token: str | None) -> bytes:
        raise AssertionError("Unexpected feed request")


def test_signed_webhooks_and_replay(
    merchant: tuple[TestClient, UUID, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    client, tenant, _ = merchant
    carrier, shop, subscriber = (secrets.token_hex(24) for _ in range(3))
    binding = IntegrationBinding(
        carrier_secret=SecretStr(carrier),
        shopify_secret=SecretStr(shop),
        outbound_url="https://example.invalid/events",
        outbound_secret=SecretStr(subscriber),
    )
    monkeypatch.setattr(settings, "integrations", {tenant: binding})
    base = f"/v1/webhooks/{tenant}/"
    body = b'{"id":123,"currency":"KES","total_price":"3.25","email":"private@example.invalid"}'
    shop_headers = {"X-Shopify-Topic": "orders/create", "X-Shopify-Webhook-Id": "message-1"}
    assert client.post(base + "shopify", content=body, headers=shop_headers).status_code == 401
    shop_headers["X-Shopify-Hmac-Sha256"] = base64.b64encode(
        hmac.digest(shop.encode(), body, "sha256")
    ).decode()
    posted = client.post(base + "shopify", content=body, headers=shop_headers)
    assert posted.status_code == 202, posted.text
    assert client.post(base + "shopify", content=body, headers=shop_headers).json() == posted.json()
    shipment = uuid4()
    update = json.dumps(
        {
            "shipment_id": str(shipment),
            "status": "delivered",
            "occurred_at": datetime.now(UTC).isoformat(),
        }
    ).encode()
    stamp = str(int(time.time()))
    headers = {
        "X-CLOS-Event-Id": "delivery-1",
        "X-CLOS-Timestamp": stamp,
        "X-CLOS-Signature": signature(carrier, stamp, "delivery-1", update),
    }
    job = client.post(base + "carrier", content=update, headers=headers)
    assert job.status_code == 202, job.text
    job_id = job.json()["job_id"]
    transport = RecordingTransport()

    async def drain() -> None:
        factory = make_session_factory(URL)
        try:
            while await consume(factory, tenant, transport):
                pass
        finally:
            await factory.kw["bind"].dispose()

    asyncio.run(drain())
    assert client.get("/v1/dead-letters").json()["items"] == [
        {"job_id": job_id, "kind": "carrier", "attempts": 1, "error_code": "LookupError"}
    ]

    async def repair() -> None:
        async with scoped(tenant) as db:
            order = (await db.scalars(select(Order))).one()
            assert order.external_ref == "shopify:123"
            db.add(Shipment(tenant_id=tenant, id=shipment, order_id=order.id))

    asyncio.run(repair())
    replay = f"/v1/dead-letters/{job_id}/replays"
    for _ in range(2):
        assert client.post(replay, headers={"Idempotency-Key": "repair-1"}).status_code == 202
    asyncio.run(drain())
    assert client.get("/v1/dead-letters").json()["items"] == []

    async def inspect_delivery() -> None:
        async with scoped(tenant) as db:
            assert await db.scalar(select(func.count()).select_from(ShipmentEvent)) == 1

    asyncio.run(inspect_delivery())
    assert len(transport.sent) == 2
    for data, outbound in transport.sent:
        event_id = outbound["Idempotency-Key"]
        assert event_id == json.loads(data)["event_id"]
        assert outbound["X-CLOS-Signature"] == signature(
            subscriber, outbound["X-CLOS-Timestamp"], event_id, data
        )
        assert b"private@" not in data


def test_pause_and_rate_limit(merchant: tuple[TestClient, UUID, str]) -> None:
    client, tenant, _ = merchant

    async def pause(enabled: bool) -> None:
        async with Redis.from_url(settings.redis_url) as redis:
            key = f"clos:pause:{tenant}"
            if enabled:
                await redis.set(key, "1", ex=30)
            else:
                await redis.delete(key)

    asyncio.run(pause(True))
    try:
        response = client.post(
            "/v1/runs", json={"message": "inventory"}, headers={"Idempotency-Key": "paused"}
        )
        assert response.status_code == 503
    finally:
        asyncio.run(pause(False))
    app.state.limiter.user_limit = 2
    assert client.get("/v1/auth/me").headers["RateLimit-Remaining"] == "0"
    exhausted = client.get("/v1/auth/me")
    assert exhausted.status_code == 429
    assert int(exhausted.headers["Retry-After"]) > 0


def test_scheduled_feeds(
    merchant: tuple[TestClient, UUID, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    _, tenant, _ = merchant
    observed = datetime.now(UTC)
    listing, shipment = uuid4(), uuid4()
    binding = IntegrationBinding(
        inventory_interval_seconds=86400,
        pricing_interval_seconds=86400,
        logistics_interval_seconds=86400,
        price_feed_url="https://example.invalid/prices",
        tracking_feed_url="https://example.invalid/tracking",
    )
    monkeypatch.setattr(settings, "integrations", {tenant: binding})
    publish = Mock()
    monkeypatch.setattr(celery_app, "send_task", publish)

    class Feeds(RecordingTransport):
        async def feed(self, url: str, token: str | None) -> bytes:
            if url == binding.price_feed_url:
                return json.dumps(
                    [{"listing_id": str(listing), "price": "15.25", "currency": "KES"}]
                ).encode()
            observation = {
                "shipment_id": str(shipment),
                "occurred_at": observed.isoformat(),
                "status": "shipped",
            }
            return json.dumps([observation, observation]).encode()

    async def verify() -> None:
        async with scoped(tenant) as db:
            product = Product(tenant_id=tenant, name="Test", sku="SAMPLE", currency="KES")
            order = Order(tenant_id=tenant, currency="KES", total=Decimal("1"))
            db.add_all([product, order])
            await db.flush()
            db.add(
                CompetitorListing(
                    tenant_id=tenant,
                    id=listing,
                    product_id=product.id,
                    source="synthetic",
                    price=Decimal("1"),
                    currency="KES",
                    observed_at=observed,
                )
            )
            db.add(Shipment(tenant_id=tenant, id=shipment, order_id=order.id))
        await tick()
        await tick()
        factory = make_session_factory(URL)
        try:
            while await consume(factory, tenant, Feeds()):
                pass
        finally:
            await factory.kw["bind"].dispose()
        async with scoped(tenant) as db:
            jobs = (await db.scalars(select(AsyncJob))).all()
            assert sorted((j.kind, j.status) for j in jobs) == [
                ("inventory", "done"),
                ("logistics", "done"),
                ("pricing", "done"),
            ]
            price = await db.get(CompetitorListing, listing)
            assert price and price.price == Decimal("15.25")
            tracked = await db.get(Shipment, shipment)
            assert tracked and tracked.status == "shipped"
            assert await db.scalar(select(func.count()).select_from(ShipmentEvent)) == 1

    asyncio.run(verify())
    publish.assert_any_call("clos.drain_delivery", args=[str(tenant)])
