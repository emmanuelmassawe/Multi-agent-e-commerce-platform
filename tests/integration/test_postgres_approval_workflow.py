"""PostgreSQL approval tenancy, idempotency, decision, and expiry checks."""

import asyncio
import os
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from clos.adapters.db.approvals import SQLApprovalWorkflow
from clos.adapters.db.models import AgentRun, ApprovalRequest, AuditLog, Tenant, User
from clos.adapters.db.session import tenant_session
from clos.application.approvals import ApprovalConflict

DATABASE_URL = os.environ.get("TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(DATABASE_URL is None, reason="TEST_DATABASE_URL is not configured")


def test_postgres_approval_is_tenant_scoped_idempotent_and_expiring() -> None:
    assert DATABASE_URL is not None

    async def scenario() -> None:
        engine = create_async_engine(DATABASE_URL)
        sessions = async_sessionmaker(engine, expire_on_commit=False)
        tenant_id, other_tenant_id = uuid4(), uuid4()
        run_id, other_run_id = uuid4(), uuid4()
        approver_id = uuid4()
        async with sessions.begin() as session:
            session.add_all(
                [
                    Tenant(id=tenant_id, slug=f"approval-{tenant_id.hex[:12]}", name="Approval"),
                    Tenant(
                        id=other_tenant_id,
                        slug=f"approval-{other_tenant_id.hex[:12]}",
                        name="Other",
                    ),
                ]
            )
        async with tenant_session(sessions, tenant_id) as session:
            session.add_all(
                [
                    AgentRun(
                        id=run_id,
                        tenant_id=tenant_id,
                        agent_name="pricing",
                        status="awaiting_approval",
                    ),
                    User(
                        id=approver_id,
                        tenant_id=tenant_id,
                        email=f"manager-{tenant_id.hex[:10]}@example.test",
                        full_name="Approval Manager",
                        password_hash="test-hash",
                        role="manager",
                    ),
                ]
            )
        async with tenant_session(sessions, other_tenant_id) as session:
            session.add(
                AgentRun(
                    id=other_run_id,
                    tenant_id=other_tenant_id,
                    agent_name="pricing",
                    status="awaiting_approval",
                )
            )

        workflow = SQLApprovalWorkflow(sessions)
        expiry = datetime.now(UTC) + timedelta(minutes=5)
        requested = await workflow.create_request(
            tenant_id,
            run_id,
            "apply_price_change",
            {"price": 20},
            {"explanation": "configured margin preserved"},
            "tool-call-1",
            expiry,
        )
        retried = await workflow.create_request(
            tenant_id,
            run_id,
            "apply_price_change",
            {"price": 20},
            {"explanation": "retry"},
            "tool-call-1",
            expiry,
        )
        assert retried.approval_id == requested.approval_id
        with pytest.raises(ApprovalConflict, match="reused with different"):
            await workflow.create_request(
                tenant_id,
                run_id,
                "apply_price_change",
                {"price": 21},
                {},
                "tool-call-1",
                expiry,
            )

        approved = await workflow.decide(
            tenant_id,
            requested.approval_id,
            approver_id,
            "approved",
            "decision-1",
            {"price": 22},
        )
        assert approved.status == "approved"
        assert await workflow.is_approved(
            tenant_id, run_id, requested.approval_id, "apply_price_change", {"price": 22}
        )
        assert not await workflow.is_approved(
            tenant_id, run_id, requested.approval_id, "apply_price_change", {"price": 20}
        )
        assert not await workflow.is_approved(
            other_tenant_id,
            run_id,
            requested.approval_id,
            "apply_price_change",
            {"price": 22},
        )

        expired = await workflow.create_request(
            tenant_id,
            run_id,
            "propose_reorder",
            {"quantity": 4},
            {},
            "tool-call-expired",
            datetime.now(UTC) - timedelta(seconds=1),
        )
        expired_items = await workflow.expire_pending(tenant_id)
        assert [item.approval_id for item in expired_items] == [expired.approval_id]
        assert expired_items[0].status == "rejected"

        async with tenant_session(sessions, tenant_id) as session:
            audits = await session.execute(
                select(AuditLog.action).where(
                    AuditLog.tenant_id == tenant_id,
                    AuditLog.entity_id == expired.approval_id,
                )
            )
            assert "approval_expired" in audits.scalars().all()
            await session.execute(
                delete(ApprovalRequest).where(ApprovalRequest.tenant_id == tenant_id)
            )
            await session.execute(delete(AuditLog).where(AuditLog.tenant_id == tenant_id))
            await session.execute(delete(AgentRun).where(AgentRun.tenant_id == tenant_id))
        async with tenant_session(sessions, other_tenant_id) as session:
            await session.execute(delete(AgentRun).where(AgentRun.tenant_id == other_tenant_id))
        async with sessions.begin() as session:
            await session.execute(delete(Tenant).where(Tenant.id.in_([tenant_id, other_tenant_id])))
        await engine.dispose()

    asyncio.run(scenario())
