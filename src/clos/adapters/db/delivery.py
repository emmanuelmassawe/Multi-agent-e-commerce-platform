"""RLS-scoped command outbox, recoverable dead letters and run journal."""

from datetime import timedelta
from random import uniform
from typing import Any
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from clos.adapters.db.models import AgentRun, AsyncJob, AuditLog, RunEvent, utc_now
from clos.adapters.db.session import tenant_session
from clos.adapters.delivery_control import check_active
from clos.application.delivery import JobConflict, fingerprint
from clos.domain.ids import new_uuid7


async def enqueue(
    db: AsyncSession, tenant: UUID, kind: str, key: str, payload: dict[str, Any]
) -> tuple[AsyncJob, bool]:
    digest = fingerprint(payload)
    key_hash = fingerprint(key)
    uid = new_uuid7()
    await db.execute(
        insert(AsyncJob)
        .values(
            id=uid,
            tenant_id=tenant,
            kind=kind,
            request_key=key_hash,
            fingerprint=digest,
            payload=payload,
        )
        .on_conflict_do_nothing(constraint="uq_async_job_key")
    )
    job = (
        await db.scalars(
            select(AsyncJob).where(
                AsyncJob.tenant_id == tenant,
                AsyncJob.kind == kind,
                AsyncJob.request_key == key_hash,
            )
        )
    ).one()
    if job.fingerprint != digest:
        raise JobConflict("Idempotency key was already used for different input")
    return job, job.id == uid


async def append_event(
    db: AsyncSession, tenant: UUID, run: UUID, kind: str, data: dict[str, Any]
) -> None:
    row = await db.scalar(
        select(AgentRun.id)
        .where(AgentRun.tenant_id == tenant, AgentRun.id == run)
        .with_for_update(key_share=True)
    )
    if row is None:
        raise LookupError("Run not found")
    last = await db.scalar(
        select(func.max(RunEvent.position)).where(
            RunEvent.run_id == run, RunEvent.tenant_id == tenant
        )
    )
    db.add(
        RunEvent(tenant_id=tenant, run_id=run, event_type=kind, position=(last or 0) + 1, data=data)
    )
    await db.flush()


async def submit_run(db: AsyncSession, tenant: UUID, key: str, message: str, actor: UUID) -> UUID:
    job, created = await enqueue(db, tenant, "run", key, {"message": message, "actor": str(actor)})
    if created:
        db.add(
            AgentRun(
                id=job.id,
                tenant_id=tenant,
                status="queued",
                agent_name="supervisor",
                autonomy_mode="shadow",
            )
        )
        db.add(
            AuditLog(
                tenant_id=tenant,
                actor_id=actor,
                action="run.submitted",
                entity_type="run",
                entity_id=job.id,
            )
        )
        await db.flush()
        await append_event(db, tenant, job.id, "run_queued", {})
    return job.id


async def replay(db: AsyncSession, tenant: UUID, job_id: UUID, actor: UUID, key: str) -> None:
    job = await db.scalar(
        select(AsyncJob)
        .where(AsyncJob.tenant_id == tenant, AsyncJob.id == job_id)
        .with_for_update()
    )
    if not job:
        raise LookupError("Job not found")
    receipt, created = await enqueue(
        db, tenant, "replay", key, {"job_id": str(job_id), "actor": str(actor)}
    )
    if not created:
        return
    if job.status != "dead":
        raise JobConflict("Job is not dead-lettered")
    receipt.status = "done"
    job.status = "pending"
    job.attempts = 0
    job.available_at = utc_now()
    job.error_code = None
    if job.kind == "run":
        run = await db.get(AgentRun, job.id)
        if run:
            run.status = "queued"
            await append_event(db, tenant, job.id, "run_queued", {"replayed": True})
    db.add(
        AuditLog(
            tenant_id=tenant,
            actor_id=actor,
            action="job.replayed",
            entity_type="async_job",
            entity_id=job_id,
        )
    )


async def failed(db: AsyncSession, job: AsyncJob, exc: Exception, maximum: int) -> None:
    job.error_code = type(exc).__name__[:80]
    if job.attempts < maximum:
        job.available_at = utc_now() + timedelta(seconds=uniform(1, min(600, 2**job.attempts)))
        return
    job.status = "dead"
    db.add(
        AuditLog(
            tenant_id=job.tenant_id,
            action="job.dead_lettered",
            entity_type="async_job",
            entity_id=job.id,
            details={"error_code": job.error_code, "attempts": job.attempts},
        )
    )
    if job.kind == "run":
        run = await db.get(AgentRun, job.id)
        if run:
            run.status = "failed"
            await append_event(
                db, job.tenant_id, job.id, "run_failed", {"error_code": job.error_code}
            )


class Journal:
    def __init__(self, sessions: async_sessionmaker[AsyncSession], tenant: UUID, run: UUID) -> None:
        self.sessions = sessions
        self.tenant = tenant
        self.run = run

    async def emit(self, kind: str, data: dict[str, Any]) -> None:
        if kind in {"node_started", "tool_started"}:
            await check_active(self.tenant)
        async with tenant_session(self.sessions, self.tenant) as db:
            await append_event(db, self.tenant, self.run, kind, data)

    async def cursor(self, event_id: UUID | None) -> int:
        async with tenant_session(self.sessions, self.tenant) as db:
            if not await db.get(AgentRun, self.run):
                raise LookupError("Run not found")
            if event_id is None:
                return 0
            value = await db.scalar(
                select(RunEvent.position).where(
                    RunEvent.tenant_id == self.tenant,
                    RunEvent.run_id == self.run,
                    RunEvent.id == event_id,
                )
            )
            if value is None:
                raise LookupError("Event cursor not found for this run")
            return value

    async def page(self, after: int) -> tuple[list[RunEvent], str]:
        async with tenant_session(self.sessions, self.tenant) as db:
            # Read status first: a concurrent terminal commit must not hide its final event.
            run = await db.get(AgentRun, self.run)
            if not run:
                raise LookupError("Run not found")
            rows = await db.scalars(
                select(RunEvent)
                .where(
                    RunEvent.tenant_id == self.tenant,
                    RunEvent.run_id == self.run,
                    RunEvent.position > after,
                )
                .order_by(RunEvent.position)
                .limit(100)
            )
            return list(rows), run.status
