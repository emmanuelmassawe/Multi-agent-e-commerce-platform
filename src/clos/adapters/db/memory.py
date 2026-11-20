"""PostgreSQL source, durable outbox and authoritative retrieval hydration."""

import hashlib
import json
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from uuid import UUID, uuid5

from sqlalchemy import Select, delete, or_, select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from clos.adapters.db.models import (
    AuditLog,
    Conversation,
    Customer,
    MemoryChunk,
    MemoryDocument,
    MemoryJob,
    Message,
)
from clos.adapters.db.session import tenant_session
from clos.agents.common import RetrievedDocument
from clos.application.memory import Point, SessionCachePort, VectorStorePort, passages
from clos.domain.ids import new_uuid7


class MemoryConflict(ValueError):
    pass


class MemoryRepository:
    def __init__(
        self,
        sessions: async_sessionmaker[AsyncSession],
        vectors: VectorStorePort,
        cache: SessionCachePort,
    ) -> None:
        self.sessions = sessions
        self.vectors = vectors
        self.cache = cache

    @asynccontextmanager
    async def locked(self, tenant: UUID) -> AsyncIterator[AsyncSession]:
        async with tenant_session(self.sessions, tenant) as db:
            await db.execute(
                text("SELECT pg_advisory_xact_lock(hashtextextended(:key, 0))"),
                {"key": f"memory:{tenant}"},
            )
            yield db

    @staticmethod
    async def customer(db: AsyncSession, tenant: UUID, customer: UUID) -> None:
        if not await db.scalar(
            select(Customer.id).where(Customer.id == customer, Customer.tenant_id == tenant)
        ):
            raise LookupError("Customer not found")

    async def submit(
        self,
        tenant: UUID,
        actor: UUID,
        key: str,
        customer: UUID | None,
        *,
        source: str | None = None,
        body: str | None = None,
    ) -> MemoryJob:
        operation = "erase" if body is None else "ingest"
        if operation == "erase" and customer is None:
            raise ValueError("Customer required")
        if body is not None and (not body.strip() or not source or not source.strip()):
            raise ValueError("Document text and source are required")
        job_id = uuid5(tenant, f"memory:{key}")
        digest = hashlib.sha256(
            json.dumps([operation, str(customer), source, body]).encode()
        ).hexdigest()
        async with self.locked(tenant) as db:
            existing = await db.get(MemoryJob, job_id)
            if existing:
                if existing.fingerprint != digest:
                    raise MemoryConflict("Idempotency key has already been used")
                return existing
            if customer:
                await self.customer(db, tenant, customer)
                if await db.scalar(
                    select(MemoryJob.id).where(
                        MemoryJob.tenant_id == tenant,
                        MemoryJob.operation == "erase",
                        MemoryJob.subject_id == customer,
                        MemoryJob.status == "pending",
                    )
                ):
                    raise MemoryConflict("Customer erasure is pending")
            subject = customer
            if body is not None:
                subject = new_uuid7()
                db.add(
                    MemoryDocument(
                        id=subject, tenant_id=tenant, customer_id=customer, source=source, body=body
                    )
                )
            job = MemoryJob(
                id=job_id,
                tenant_id=tenant,
                subject_id=subject,
                fingerprint=digest,
                operation=operation,
                status="pending",
            )
            db.add_all(
                [
                    job,
                    AuditLog(
                        tenant_id=tenant,
                        actor_id=actor,
                        action=f"memory.{operation}.requested",
                        entity_type="memory_job",
                        entity_id=job_id,
                    ),
                ]
            )
            await db.flush()
            return job

    async def job(self, tenant: UUID, job_id: UUID) -> MemoryJob:
        async with tenant_session(self.sessions, tenant) as db:
            job = await db.get(MemoryJob, job_id)
            if job is None:
                raise LookupError("Memory job not found")
            return job

    async def process_next(self, tenant: UUID) -> bool:
        async with self.locked(tenant) as db:
            job = await db.scalar(
                select(MemoryJob)
                .where(MemoryJob.tenant_id == tenant, MemoryJob.status == "pending")
                .order_by(MemoryJob.created_at, MemoryJob.id)
                .limit(1)
            )
            if not job:
                return False
            assert job.subject_id is not None
            if job.operation == "erase":
                await self._erase(db, tenant, job.subject_id)
            else:
                doc = await db.get(MemoryDocument, job.subject_id)
                if doc:
                    points = []
                    for index, passage in enumerate(passages(doc.body)):
                        uid = uuid5(doc.id, str(index))
                        db.add(
                            MemoryChunk(id=uid, tenant_id=tenant, document_id=doc.id, body=passage)
                        )
                        points.append(Point(uid, tenant, doc.customer_id, passage))
                    await self.vectors.upsert(points)
            job.status = "completed"
            db.add(
                AuditLog(
                    tenant_id=tenant,
                    action=f"memory.{job.operation}.completed",
                    entity_type="memory_job",
                    entity_id=job.id,
                )
            )
            job.subject_id = None
            return True

    @staticmethod
    def _conversations(tenant: UUID, customer: UUID) -> Select[UUID]:
        return select(Conversation.id).where(
            Conversation.tenant_id == tenant, Conversation.customer_id == customer
        )

    async def _erase(self, db: AsyncSession, tenant: UUID, customer: UUID) -> None:
        await self.vectors.erase(tenant, customer)
        await self.cache.erase(tenant, customer)
        await db.execute(
            delete(Message).where(
                Message.tenant_id == tenant,
                Message.conversation_id.in_(self._conversations(tenant, customer)),
            )
        )
        await db.execute(
            delete(Conversation).where(
                Conversation.tenant_id == tenant, Conversation.customer_id == customer
            )
        )
        await db.execute(
            delete(MemoryDocument).where(
                MemoryDocument.tenant_id == tenant, MemoryDocument.customer_id == customer
            )
        )

    async def export(
        self, tenant: UUID, customer: UUID, actor: UUID
    ) -> dict[str, list[dict[str, str]]]:
        async with self.locked(tenant) as db:
            await self.customer(db, tenant, customer)
            docs = await db.scalars(
                select(MemoryDocument)
                .where(MemoryDocument.tenant_id == tenant, MemoryDocument.customer_id == customer)
                .order_by(MemoryDocument.id)
            )
            msgs = await db.scalars(
                select(Message)
                .where(
                    Message.tenant_id == tenant,
                    Message.conversation_id.in_(self._conversations(tenant, customer)),
                )
                .order_by(Message.created_at, Message.id)
            )
            db.add(
                AuditLog(
                    tenant_id=tenant,
                    actor_id=actor,
                    action="memory.export",
                    entity_type="customer",
                    entity_id=customer,
                )
            )
            return {
                "documents": [{"id": str(d.id), "source": d.source, "text": d.body} for d in docs],
                "messages": [
                    {
                        "id": str(m.id),
                        "conversation_id": str(m.conversation_id),
                        "direction": m.direction,
                        "text": m.body,
                    }
                    for m in msgs
                ],
            }

    async def append(
        self, tenant: UUID, customer: UUID, actor: UUID, key: str, direction: str, body: str
    ) -> UUID:
        conv = uuid5(tenant, f"support:{customer}")
        message_id = uuid5(tenant, f"support-message:{key}")
        digest = hashlib.sha256(json.dumps([str(customer), direction, body]).encode()).hexdigest()
        async with self.locked(tenant) as db:
            await self.customer(db, tenant, customer)
            if await db.scalar(
                select(MemoryJob.id).where(
                    MemoryJob.tenant_id == tenant,
                    MemoryJob.operation == "erase",
                    MemoryJob.subject_id == customer,
                    MemoryJob.status == "pending",
                )
            ):
                raise MemoryConflict("Customer erasure is pending")
            receipt = await db.get(MemoryJob, message_id)
            if receipt:
                if receipt.fingerprint != digest:
                    raise MemoryConflict("Idempotency key has already been used")
                return message_id
            if await db.get(Conversation, conv) is None:
                db.add(Conversation(id=conv, tenant_id=tenant, customer_id=customer))
                await db.flush()
            db.add(
                Message(
                    id=message_id,
                    tenant_id=tenant,
                    conversation_id=conv,
                    direction=direction,
                    body=body,
                    created_by=actor,
                )
            )
            db.add(
                MemoryJob(
                    id=message_id,
                    tenant_id=tenant,
                    operation="message",
                    fingerprint=digest,
                    status="completed",
                )
            )
            return message_id

    async def context(self, tenant: UUID, customer: UUID) -> str:
        async with self.locked(tenant) as db:
            await self.customer(db, tenant, customer)
            messages = list(
                await db.scalars(
                    select(Message)
                    .where(
                        Message.tenant_id == tenant,
                        Message.conversation_id.in_(self._conversations(tenant, customer)),
                    )
                    .order_by(Message.created_at.desc(), Message.id.desc())
                    .limit(24)
                )
            )
            # Include revisions so edits and deletions invalidate cached summaries.
            stamp = hashlib.sha256(
                json.dumps([(str(m.id), str(m.updated_at)) for m in messages]).encode()
            ).hexdigest()
            cached = await self.cache.read(tenant, customer)
            if cached and cached.startswith(stamp + "\n"):
                return cached.split("\n", 1)[1]
            ordered = list(reversed(messages))
            summary = " ".join(m.body.split(". ", 1)[0][:80] for m in ordered[:-4])
            result = "\n".join(filter(None, [summary, *(m.body[:500] for m in ordered[-4:])]))
            await self.cache.write(tenant, customer, stamp + "\n" + result)
            return result

    async def search(
        self, tenant_id: UUID, customer_id: UUID, query: str, *, limit: int
    ) -> list[RetrievedDocument]:
        async with tenant_session(self.sessions, tenant_id) as db:
            await self.customer(db, tenant_id, customer_id)
            ids = await self.vectors.query(tenant_id, customer_id, query, limit)
            rows = await db.execute(
                select(MemoryChunk, MemoryDocument)
                .join(MemoryDocument, MemoryChunk.document_id == MemoryDocument.id)
                .where(
                    MemoryChunk.id.in_(ids),
                    MemoryChunk.tenant_id == tenant_id,
                    MemoryDocument.tenant_id == tenant_id,
                    or_(
                        MemoryDocument.customer_id == customer_id,
                        MemoryDocument.customer_id.is_(None),
                    ),
                )
            )
            found = {c.id: RetrievedDocument(d.id, c.body, d.source) for c, d in rows}
            return [found[uid] for uid in ids if uid in found]

    async def reconcile(self, tenant: UUID, *, repair: bool) -> dict[str, int]:
        async with self.locked(tenant) as db:
            rows = await db.execute(
                select(MemoryChunk, MemoryDocument.customer_id)
                .join(MemoryDocument, MemoryDocument.id == MemoryChunk.document_id)
                .where(MemoryChunk.tenant_id == tenant, MemoryDocument.tenant_id == tenant)
            )
            points = [Point(c.id, tenant, customer, c.body) for c, customer in rows]
            actual = await self.vectors.manifest(tenant)
            expected = {p.id: p.checksum for p in points}
            extra = actual.keys() - expected.keys()
            missing = expected.keys() - actual.keys()
            changed = sum(expected[k] != actual[k] for k in expected.keys() & actual.keys())
            if extra or missing or changed:
                db.add(
                    AuditLog(
                        tenant_id=tenant,
                        action="memory.drift",
                        entity_type="index",
                        details={
                            "unexpected": len(extra),
                            "missing": len(missing),
                            "changed": changed,
                        },
                    )
                )
            if repair:
                await self.vectors.upsert(points)
                await self.vectors.remove(tenant, list(extra))
            return {
                "expected": len(points),
                "indexed": len(actual),
                "missing": len(missing),
                "unexpected": len(extra),
                "changed": changed,
            }
