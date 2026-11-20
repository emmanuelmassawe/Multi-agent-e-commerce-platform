"""Periodic durable outbox dispatch and operator-requested index maintenance."""

import asyncio
from uuid import UUID

from sqlalchemy import select

from clos.adapters.db.models import Tenant
from clos.adapters.db.session import make_session_factory
from clos.adapters.memory_runtime import memory_runtime
from clos.apps.worker.main import celery_app
from clos.config import settings


async def dispatch() -> None:
    if not settings.database_url:
        raise RuntimeError("DATABASE_URL is required")
    sessions = make_session_factory(settings.database_url)
    try:
        async with sessions() as db:
            tenants = await db.scalars(select(Tenant.id))
            for tenant in tenants:
                celery_app.send_task("clos.memory_job", args=[str(tenant), "drain"])
    finally:
        await sessions.kw["bind"].dispose()


@celery_app.task(name="clos.dispatch_memory")  # type: ignore[untyped-decorator]
def dispatch_task() -> None:
    asyncio.run(dispatch())


async def work(tenant: UUID, operation: str) -> dict[str, int]:
    if not settings.database_url:
        raise RuntimeError("DATABASE_URL is required")
    sessions = make_session_factory(settings.database_url)
    try:
        async with memory_runtime(sessions) as repo:
            if operation in ("reindex", "drift"):
                return await repo.reconcile(tenant, repair=operation == "reindex")
            if operation != "drain":
                raise ValueError("Unknown memory operation")
            count = 0
            while count < 25 and await repo.process_next(tenant):
                count += 1
            return {"delivered": count}
    finally:
        await sessions.kw["bind"].dispose()


@celery_app.task(
    name="clos.memory_job",
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_jitter=True,
    max_retries=3,
)  # type: ignore[untyped-decorator]
def memory_job(tenant: str, operation: str) -> dict[str, int]:
    return asyncio.run(work(UUID(tenant), operation))


if __name__ == "__main__":
    import argparse
    import json

    parser = argparse.ArgumentParser(description="Inspect and rebuild a tenant memory index")
    parser.add_argument("operation", choices=["drift", "reindex"])
    parser.add_argument("tenant", type=UUID)
    args = parser.parse_args()
    print(json.dumps(asyncio.run(work(args.tenant, args.operation))))
