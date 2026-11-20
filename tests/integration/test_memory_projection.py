"""Real PostgreSQL, Qdrant and Redis exercise the same projection used by the API."""

import asyncio
import os
from collections.abc import Awaitable, Callable
from unittest.mock import patch
from uuid import uuid4

import pytest
from sqlalchemy import delete, select

from clos.adapters.db.memory import MemoryConflict
from clos.adapters.db.models import AuditLog, Customer, Tenant, User
from clos.adapters.db.session import make_session_factory, tenant_session
from clos.adapters.memory_runtime import memory_runtime
from clos.application.memory import Point

URL = os.getenv("TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(
    not URL or not os.getenv("TEST_MEMORY_SERVICES"), reason="Phase 5 integration services required"
)


def test_memory_projection() -> None:
    asyncio.run(scenario())


async def scenario() -> None:
    assert URL
    sessions = make_session_factory(URL)
    a, b, alice, bob, actor, other_actor = (uuid4() for _ in range(6))
    try:
        async with sessions.begin() as db:
            db.add_all([Tenant(id=t, slug=t.hex, name="memory test") for t in (a, b)])
        for t, u, customer in [(a, actor, alice), (b, other_actor, bob)]:
            async with tenant_session(sessions, t) as db:
                db.add(
                    User(
                        id=u,
                        tenant_id=t,
                        email="test@example.invalid",
                        full_name="Test",
                        password_hash="unused",
                        role="owner",
                    )
                )
                db.add(Customer(id=customer, tenant_id=t, display_name="test"))
        stranger = uuid4()
        async with tenant_session(sessions, a) as db:
            db.add(Customer(id=stranger, tenant_id=a, display_name="test"))
        async with memory_runtime(sessions) as repo:
            for t, u, c, body in [
                (a, actor, alice, "private alice"),
                (a, actor, stranger, "private stranger"),
                (b, other_actor, bob, "private bob"),
                (a, actor, None, "shared policy"),
            ]:
                job = await repo.submit(t, u, body, c, source="fixture", body=body)
                assert (await repo.submit(t, u, body, c, source="fixture", body=body)).id == job.id
                if c == alice:
                    upsert = repo.vectors.upsert

                    async def lose_ack(
                        points: list[Point],
                        write: Callable[[list[Point]], Awaitable[None]] = upsert,
                    ) -> None:
                        await write(points)
                        raise ConnectionError("Simulated lost acknowledgement")

                    with patch.object(repo.vectors, "upsert", side_effect=lose_ack):
                        with pytest.raises(ConnectionError):
                            await repo.process_next(t)
                    assert (await repo.job(t, job.id)).status == "pending"
                    assert not await repo.search(t, alice, "private", limit=5)
                assert await repo.process_next(t)
                assert not await repo.process_next(t)
            with pytest.raises(MemoryConflict):
                await repo.submit(
                    a, actor, "private alice", alice, source="fixture", body="different"
                )
            with pytest.raises(LookupError):
                await repo.search(b, alice, "private", limit=5)
            hits = await repo.search(a, alice, "private", limit=5)
            assert hits[0].text == "private alice"
            assert {h.text for h in hits} == {"shared policy", "private alice"}
            baseline = await repo.vectors.manifest(a)
            assert len(baseline) == 3
            await repo.vectors.remove(a, [next(iter(baseline))])
            await repo.vectors.upsert([Point(uuid4(), a, alice, "orphan")])
            drift = await repo.reconcile(a, repair=False)
            assert drift["missing"] == drift["unexpected"] == 1
            await repo.reconcile(a, repair=True)
            assert await repo.vectors.manifest(a) == baseline
            assert hits == await repo.search(a, alice, "private", limit=5)
            await repo.append(a, alice, actor, "message", "inbound", "question")
            assert await repo.context(a, alice) == "question"
            assert await repo.context(a, alice) == "question"
            assert len((await repo.export(a, alice, actor))["documents"]) == 1
            erase = await repo.submit(a, actor, "delete", alice)
            assert await repo.process_next(a)
            assert (await repo.job(a, erase.id)).status == "completed"
            assert (await repo.submit(a, actor, "delete", alice)).status == "completed"
            await repo.append(a, alice, actor, "message", "inbound", "question")
            assert await repo.export(a, alice, actor) == {"messages": [], "documents": []}
            assert await repo.cache.read(a, alice) is None
            assert len(await repo.vectors.manifest(a)) == 2
            assert len(await repo.vectors.manifest(b)) == 1
            assert [h.text for h in await repo.search(a, alice, "policy", limit=5)] == [
                "shared policy"
            ]
            async with tenant_session(sessions, a) as db:
                assert await db.scalar(
                    select(AuditLog.id).where(
                        AuditLog.entity_id == erase.id, AuditLog.action == "memory.erase.completed"
                    )
                )
    finally:
        async with memory_runtime(sessions) as repo:
            for t in (a, b):
                await repo.vectors.remove(t, list(await repo.vectors.manifest(t)))
        for t in (a, b):
            async with tenant_session(sessions, t) as db:
                await db.execute(delete(Tenant).where(Tenant.id == t))
        await sessions.kw["bind"].dispose()
