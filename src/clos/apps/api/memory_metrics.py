"""Aggregate operational metrics. Source text and tenant identifiers stay out of labels."""

from datetime import UTC, datetime

from fastapi import APIRouter, Request, Response
from prometheus_client import (
    CONTENT_TYPE_LATEST,
    CollectorRegistry,
    Counter,
    Gauge,
    Histogram,
    generate_latest,
)
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from clos.adapters.db.models import AsyncJob, AuditLog, MemoryJob, Tenant
from clos.adapters.db.session import tenant_session

router = APIRouter()
registry = CollectorRegistry()
retrieval_seconds = Histogram(
    "retrieval_latency_seconds", "Support retrieval and SQL hydration time", registry=registry
)
empty_results = Counter(
    "retrieval_empty_total", "Completed searches without evidence", registry=registry
)


@router.get("/metrics", include_in_schema=False)
async def metrics(request: Request) -> Response:
    data = generate_latest(registry)
    sessions: async_sessionmaker[AsyncSession] | None = getattr(
        request.app.state, "session_factory", None
    )
    if sessions is not None:
        snapshot = CollectorRegistry()
        delivery = Gauge(
            "delivery_jobs", "Durable jobs awaiting work or replay", ["status"], registry=snapshot
        )
        totals = {"pending": 0, "dead": 0}
        oldest = 0.0
        drift = 0
        async with sessions() as db:
            tenants = list(await db.scalars(select(Tenant.id)))
        for tenant in tenants:
            async with tenant_session(sessions, tenant) as db:
                counts = await db.execute(
                    select(AsyncJob.status, func.count())
                    .where(AsyncJob.tenant_id == tenant, AsyncJob.status.in_(tuple(totals)))
                    .group_by(AsyncJob.status)
                )
                for status, count in counts:
                    totals[status] += count
                pending = await db.scalar(
                    select(func.min(MemoryJob.created_at)).where(
                        MemoryJob.tenant_id == tenant, MemoryJob.status == "pending"
                    )
                )
                if pending:
                    oldest = max(oldest, (datetime.now(UTC) - pending).total_seconds())
                drift += (
                    await db.scalar(
                        select(func.count())
                        .select_from(AuditLog)
                        .where(AuditLog.tenant_id == tenant, AuditLog.action == "memory.drift")
                    )
                    or 0
                )
        for status, count in totals.items():
            delivery.labels(status).set(count)
        Gauge("outbox_lag_seconds", "Age of oldest pending memory job", registry=snapshot).set(
            oldest
        )
        Counter(
            "qdrant_drift_total", "Recorded checks that found index drift", registry=snapshot
        ).inc(drift)
        data += generate_latest(snapshot)
    return Response(data, headers={"Content-Type": CONTENT_TYPE_LATEST})
