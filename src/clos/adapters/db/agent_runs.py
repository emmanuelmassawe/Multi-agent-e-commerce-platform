"""Tenant-scoped AgentRun and TokenUsage persistence for orchestration."""

from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from clos.adapters.db.models import AgentRun, TokenUsage
from clos.adapters.db.delivery import append_event, enqueue
from clos.config import settings
from clos.adapters.db.session import tenant_session
from clos.agents.supervisor.graph import UsageRecord


class AgentRunNotFound(LookupError):
    """The requested run is not owned by the supplied tenant."""


class SQLAgentRunRepository:
    def __init__(self, sessions: async_sessionmaker[AsyncSession]) -> None:
        self._sessions = sessions

    async def create(self, tenant_id: UUID, run_id: UUID) -> None:
        async with tenant_session(self._sessions, tenant_id) as session:
            session.add(
                AgentRun(
                    id=run_id,
                    tenant_id=tenant_id,
                    agent_name="supervisor",
                    status="running",
                    autonomy_mode="shadow",
                )
            )

    async def start(self, tenant_id: UUID, run_id: UUID) -> None:
        async with tenant_session(self._sessions, tenant_id) as session:
            result = await session.execute(
                select(AgentRun).where(AgentRun.id == run_id, AgentRun.tenant_id == tenant_id)
            )
            run = result.scalar_one_or_none()
            if run is None:
                session.add(
                    AgentRun(
                        id=run_id,
                        tenant_id=tenant_id,
                        agent_name="supervisor",
                        status="running",
                        autonomy_mode="shadow",
                    )
                )
            else:
                run.status = "running"
            await session.flush()
            await append_event(session,tenant_id,run_id,"run_started",{})

    async def finish(
        self,
        tenant_id: UUID,
        run_id: UUID,
        *,
        status: str,
        explanation: dict[str, Any],
        usage_records: list[UsageRecord],
    ) -> None:
        async with tenant_session(self._sessions, tenant_id) as session:
            result = await session.execute(
                select(AgentRun).where(AgentRun.id == run_id, AgentRun.tenant_id == tenant_id)
            )
            run = result.scalar_one_or_none()
            if run is None:
                raise AgentRunNotFound("Agent run not found in tenant scope")
            run.status = status
            run.explanation = explanation
            event = {"completed":"run_finished","awaiting_approval":"awaiting_approval"}.get(status,"run_failed")
            await append_event(session,tenant_id,run_id,event,{"status":status})
            binding=settings.integrations.get(tenant_id)
            if binding and binding.outbound_url:
                await enqueue(session,tenant_id,"outbound",f"{run_id}:{event}",{"subject_id":str(run_id),"event_type":event})
            await session.execute(
                delete(TokenUsage).where(
                    TokenUsage.tenant_id == tenant_id,
                    TokenUsage.agent_run_id == run_id,
                )
            )
            for record in usage_records:
                if record["tenant_id"] != str(tenant_id) or record["run_id"] != str(run_id):
                    raise ValueError("Token usage record does not match the run tenant and ID")
                session.add(
                    TokenUsage(
                        tenant_id=tenant_id,
                        agent_run_id=run_id,
                        model=record["model"],
                        input_tokens=record["input_tokens"],
                        output_tokens=record["output_tokens"],
                        cost_usd=(
                            Decimal(str(record["cost_usd"]))
                            if record["cost_usd"] is not None
                            else None
                        ),
                    )
                )
