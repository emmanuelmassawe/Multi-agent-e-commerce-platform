"""Postgres-backed tool idempotency and tenant policy integration checks."""

import asyncio
import os
from uuid import uuid4

import pytest
from pydantic import BaseModel
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from clos.adapters.db.models import AgentRun, Tenant, ToolCall
from clos.adapters.db.session import tenant_session
from clos.adapters.db.tool_idempotency import SQLToolIdempotencyStore
from clos.agents.budgets import BudgetEnforcer, BudgetLimits
from clos.agents.tools import ToolContext, ToolRegistry, ToolSpec
from clos.domain.identity import RiskLevel

DATABASE_URL = os.environ.get("TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(DATABASE_URL is None, reason="TEST_DATABASE_URL is not configured")


class Input(BaseModel):
    value: int


def test_tool_result_is_persisted_and_not_executed_twice() -> None:
    assert DATABASE_URL is not None

    async def scenario() -> None:
        engine = create_async_engine(DATABASE_URL)
        sessions = async_sessionmaker(engine, expire_on_commit=False)
        tenant_id, run_id = uuid4(), uuid4()
        async with sessions.begin() as session:
            tenant = Tenant(id=tenant_id, slug=f"tool-{uuid4().hex[:12]}", name="Tool Test")
            session.add(tenant)
        async with tenant_session(sessions, tenant_id) as session:
            session.add(
                AgentRun(
                    id=run_id,
                    tenant_id=tenant_id,
                    agent_name="supervisor",
                    status="running",
                    autonomy_mode="shadow",
                )
            )

        calls = 0

        async def handler(data: BaseModel, _context: ToolContext) -> object:
            nonlocal calls
            calls += 1
            return {"value": data.value}  # type: ignore[attr-defined]

        registry = ToolRegistry(SQLToolIdempotencyStore(sessions), BudgetEnforcer(BudgetLimits()))
        registry.register(ToolSpec("db_read", Input, RiskLevel.READ, handler))
        context = ToolContext(tenant_id, run_id, "same-request")
        first = await registry.execute("db_read", {"value": 10}, context)
        second = await registry.execute("db_read", {"value": 10}, context)
        assert first == second == {"value": 10}
        assert calls == 1
        async with tenant_session(sessions, tenant_id) as session:
            rows = await session.execute(select(ToolCall).where(ToolCall.tenant_id == tenant_id))
            records = rows.scalars().all()
            assert len(records) == 1
            assert records[0].status == "completed"
            assert records[0].output_data == {"value": {"value": 10}}
        async with tenant_session(sessions, tenant_id) as session:
            await session.execute(delete(ToolCall).where(ToolCall.tenant_id == tenant_id))
            await session.execute(delete(AgentRun).where(AgentRun.tenant_id == tenant_id))
        async with sessions.begin() as session:
            await session.execute(delete(Tenant).where(Tenant.id == tenant_id))
        await engine.dispose()

    asyncio.run(scenario())
