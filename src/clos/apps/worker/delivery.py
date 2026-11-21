"""Celery triggers backed by the durable tenant outbox and dead-letter queue."""

import asyncio
import selectors
import sys
import time
from datetime import timedelta
from uuid import UUID

from pydantic import TypeAdapter
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from clos.adapters.db.delivery import enqueue, failed
from clos.adapters.db.models import (
    AgentRun,
    AsyncJob,
    AuditLog,
    AutonomySetting,
    CompetitorListing,
    InventoryItem,
    Order,
    Shipment,
    ShipmentEvent,
    Tenant,
    utc_now,
)
from clos.adapters.db.session import make_session_factory, tenant_session
from clos.adapters.delivery_control import DeliveryPaused, check_active, circuit_open, cool_down
from clos.adapters.integration_http import HttpTransport, deliver
from clos.application.integration_events import (
    IntegrationTransport,
    OrderCreated,
    PriceObservation,
    TrackingUpdate,
)
from clos.apps.worker.main import celery_app
from clos.apps.worker.tasks import _execute
from clos.config import IntegrationBinding, settings


def sessions() -> async_sessionmaker[AsyncSession]:
    if not settings.database_url:
        raise RuntimeError("DATABASE_URL is required")
    return make_session_factory(settings.database_url)


async def apply_event(db: AsyncSession, job: AsyncJob) -> UUID:
    if job.kind == "shopify":
        body = OrderCreated.model_validate(job.payload)
        ref = f"shopify:{body.id}"
        # Only orders/create is subscribed. Concurrent sender retries share the command key.
        order = await db.scalar(
            select(Order).where(Order.tenant_id == job.tenant_id, Order.external_ref == ref)
        )
        if order is None:
            order = Order(
                tenant_id=job.tenant_id,
                external_ref=ref,
                currency=body.currency,
                total=body.total_price,
            )
            db.add(order)
            await db.flush()
        return order.id
    update = TrackingUpdate.model_validate(job.payload)
    shipment = await db.scalar(
        select(Shipment)
        .where(Shipment.id == update.shipment_id, Shipment.tenant_id == job.tenant_id)
        .with_for_update()
    )
    if not shipment:
        raise LookupError("Unknown shipment")
    last = await db.scalar(
        select(func.max(ShipmentEvent.occurred_at)).where(
            ShipmentEvent.tenant_id == job.tenant_id, ShipmentEvent.shipment_id == shipment.id
        )
    )
    db.add(
        ShipmentEvent(
            tenant_id=job.tenant_id,
            shipment_id=shipment.id,
            event_type="carrier_tracking",
            occurred_at=update.occurred_at,
            payload={"status": update.status},
        )
    )
    if not last or update.occurred_at >= last:
        shipment.status = update.status
    return shipment.id


async def scan(
    db: AsyncSession, job: AsyncJob, binding: IntegrationBinding, transport: IntegrationTransport
) -> None:
    tenant = job.tenant_id
    if job.kind == "inventory":
        count = await db.scalar(
            select(func.count())
            .select_from(InventoryItem)
            .where(InventoryItem.tenant_id == tenant, InventoryItem.quantity <= 0)
        )
        details: dict[str, object] = {"out_of_stock": count or 0}
    else:
        url = binding.price_feed_url if job.kind == "pricing" else binding.tracking_feed_url
        if not url:
            raise ValueError("Scheduled feed not configured")
        body = await transport.feed(
            url, binding.feed_token.get_secret_value() if binding.feed_token else None
        )
        observations: list[dict[str, object]] = []
        if job.kind == "pricing":
            for price in TypeAdapter(list[PriceObservation]).validate_json(body):
                listing = await db.get(CompetitorListing, price.listing_id)
                if listing and listing.currency == price.currency:
                    observations.append(
                        {
                            "listing_id": str(listing.id),
                            "price": str(price.price),
                            "currency": price.currency,
                        }
                    )
        else:
            for track in TypeAdapter(list[TrackingUpdate]).validate_json(body):
                if await db.get(Shipment, track.shipment_id):
                    observations.append(track.model_dump(mode="json"))
        details = {"observations": observations}
    db.add(
        AuditLog(
            tenant_id=tenant,
            action=f"schedule.{job.kind}",
            entity_type="async_job",
            entity_id=job.id,
            details=details,
        )
    )


async def process(db: AsyncSession, job: AsyncJob, transport: IntegrationTransport) -> None:
    binding = settings.integrations.get(job.tenant_id, IntegrationBinding())
    if job.kind == "run":
        run = await db.get(AgentRun, job.id)
        if not run:
            raise LookupError("Run missing")
        if run.status not in {"completed", "budget_exceeded", "awaiting_approval"}:
            await _execute(job.tenant_id, job.id, job.payload["message"])
    elif job.kind == "outbound":
        await deliver(transport, binding, job.tenant_id, job.id, job.payload)
    elif job.kind in {"shopify", "carrier"}:
        subject = await apply_event(db, job)
        db.add(
            AuditLog(
                tenant_id=job.tenant_id,
                action=f"webhook.{job.kind}",
                entity_type="integration",
                entity_id=subject,
                details={"job_id": str(job.id)},
            )
        )
        if binding.outbound_url:
            await enqueue(
                db,
                job.tenant_id,
                "outbound",
                str(job.id),
                {"subject_id": str(subject), "event_type": job.kind + ".received"},
            )
    elif job.kind in {"pricing", "logistics", "inventory"}:
        mode = await db.scalar(
            select(AutonomySetting.mode).where(
                AutonomySetting.tenant_id == job.tenant_id, AutonomySetting.agent_name == job.kind
            )
        )
        if mode != "off":
            await scan(db, job, binding, transport)
    else:
        raise ValueError("Unsupported command")


async def consume(
    factory: async_sessionmaker[AsyncSession], tenant: UUID, transport: IntegrationTransport
) -> bool:
    try:
        await check_active(tenant)
    except DeliveryPaused:
        return False
    async with tenant_session(factory, tenant) as db:
        job = await db.scalar(
            select(AsyncJob)
            .where(
                AsyncJob.tenant_id == tenant,
                AsyncJob.status == "pending",
                AsyncJob.available_at <= utc_now(),
            )
            .order_by(AsyncJob.available_at, AsyncJob.id)
            .limit(1)
            .with_for_update(skip_locked=True)
        )
        if not job:
            return False
        external = job.kind in {"outbound", "pricing", "logistics"}
        if external and await circuit_open(tenant, job.kind):
            job.available_at = utc_now() + timedelta(seconds=30)
            return True
        job.attempts += 1
        try:
            async with db.begin_nested(), asyncio.timeout(120):
                await process(db, job, transport)
        except DeliveryPaused:
            job.attempts -= 1
            job.available_at = utc_now() + timedelta(seconds=2)
        except Exception as exc:
            if external and job.attempts >= 3:
                await cool_down(tenant, job.kind)
            await failed(db, job, exc, settings.delivery_max_attempts)
        else:
            job.status = "done"
            job.error_code = None
            job.payload = {}
        return True


async def tick() -> None:
    factory = sessions()
    try:
        async with factory() as db:
            tenants = list(await db.scalars(select(Tenant.id).where(Tenant.is_active.is_(True))))
        for tenant in tenants:
            try:
                await check_active(tenant)
            except DeliveryPaused:
                continue
            async with tenant_session(factory, tenant) as db:
                binding = settings.integrations.get(tenant, IntegrationBinding())
                for kind, interval in (
                    ("inventory", binding.inventory_interval_seconds),
                    ("pricing", binding.pricing_interval_seconds),
                    ("logistics", binding.logistics_interval_seconds),
                ):
                    if interval:
                        slot = int(time.time()) // interval
                        await enqueue(db, tenant, kind, str(slot), {"slot": slot})
                due = await db.scalar(
                    select(AsyncJob.id)
                    .where(
                        AsyncJob.tenant_id == tenant,
                        AsyncJob.status == "pending",
                        AsyncJob.available_at <= utc_now(),
                    )
                    .limit(1)
                )
            if due:
                await asyncio.to_thread(
                    celery_app.send_task, "clos.drain_delivery", args=[str(tenant)]
                )
    finally:
        await factory.kw["bind"].dispose()


@celery_app.task(name="clos.dispatch_delivery")  # type: ignore[untyped-decorator]
def dispatch_delivery() -> None:
    asyncio.run(tick())


async def drain(tenant: UUID) -> int:
    factory = sessions()
    try:
        n = 0
        while n < 10 and await consume(factory, tenant, HttpTransport()):
            n += 1
        return n
    finally:
        await factory.kw["bind"].dispose()


@celery_app.task(name="clos.drain_delivery")  # type: ignore[untyped-decorator]
def drain_delivery(tenant: str) -> int:
    if sys.platform == "win32":
        return asyncio.run(
            drain(UUID(tenant)),
            loop_factory=lambda: asyncio.SelectorEventLoop(selectors.SelectSelector()),
        )
    return asyncio.run(drain(UUID(tenant)))
