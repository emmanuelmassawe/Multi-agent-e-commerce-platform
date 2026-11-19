"""Celery task that executes and resumes supervisor graphs."""

import asyncio
import math
from datetime import UTC, datetime
from uuid import UUID

from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from sqlalchemy.engine import make_url

from clos.adapters.db.agent_runs import SQLAgentRunRepository
from clos.adapters.db.approvals import SQLApprovalWorkflow
from clos.adapters.db.session import make_session_factory
from clos.adapters.llm.factory import build_worker_llm
from clos.adapters.notifications import AuditStreamNotifier
from clos.agents.supervisor.graph import build_supervisor_graph
from clos.application.approvals import ApprovalItem, ApprovalService
from clos.application.runs import execute_supervisor_run
from clos.apps.worker.main import celery_app
from clos.config import settings


def _psycopg_url(url: str) -> str:
    return make_url(url).set(drivername="postgresql").render_as_string(hide_password=False)


async def _execute(tenant_id: UUID, run_id: UUID, message: str) -> dict[str, object]:
    if settings.database_url is None:
        raise RuntimeError("DATABASE_URL is required by the agent worker")
    llm = build_worker_llm(settings)
    factory = make_session_factory(settings.database_url)
    try:
        async with AsyncPostgresSaver.from_conn_string(
            _psycopg_url(settings.database_url)
        ) as saver:
            graph = build_supervisor_graph(llm, checkpointer=saver)
            return await execute_supervisor_run(
                graph,
                SQLAgentRunRepository(factory),
                tenant_id=tenant_id,
                run_id=run_id,
                message=message,
            )
    finally:
        close = getattr(llm, "aclose", None)
        if close is not None:
            await close()
        await factory.kw["bind"].dispose()


class CeleryRunResumer:
    async def resume(self, item: ApprovalItem) -> None:
        payload: dict[str, object] = {
            "approval_id": str(item.approval_id),
            "decision": item.status,
        }
        if item.status == "approved":
            payload["tool_input"] = item.context.get("tool_input", {})
        celery_app.send_task(
            "clos.resume_supervisor_run", args=[str(item.tenant_id), str(item.run_id), payload]
        )


async def _resume(tenant_id: UUID, run_id: UUID, decision: dict[str, object]) -> dict[str, object]:
    if settings.database_url is None:
        raise RuntimeError("DATABASE_URL is required by the agent worker")
    llm = build_worker_llm(settings)
    factory = make_session_factory(settings.database_url)
    try:
        async with AsyncPostgresSaver.from_conn_string(
            _psycopg_url(settings.database_url)
        ) as saver:
            graph = build_supervisor_graph(llm, checkpointer=saver)
            return await execute_supervisor_run(
                graph,
                SQLAgentRunRepository(factory),
                tenant_id=tenant_id,
                run_id=run_id,
                message="",
                resume=decision,
            )
    finally:
        close = getattr(llm, "aclose", None)
        if close is not None:
            await close()
        await factory.kw["bind"].dispose()


async def _expire_approvals(tenant_id: UUID, approval_id: UUID) -> int:
    if settings.database_url is None:
        raise RuntimeError("DATABASE_URL is required by the agent worker")
    factory = make_session_factory(settings.database_url)
    try:
        workflow = SQLApprovalWorkflow(factory)
        service = ApprovalService(
            workflow,
            AuditStreamNotifier(),
            resumer=CeleryRunResumer(),
        )
        expired = await service.expire_due(tenant_id)
        request = await workflow.get_request(tenant_id, approval_id)
        if request is not None and request.status == "pending":
            remaining = max(1, math.ceil((request.expires_at - datetime.now(UTC)).total_seconds()))
            celery_app.send_task(
                "clos.expire_approval_request",
                args=[str(tenant_id), str(approval_id)],
                countdown=remaining,
            )
        return len(expired)
    finally:
        await factory.kw["bind"].dispose()


# Celery ships without typing metadata; task behavior is covered through its registered config.
@celery_app.task(  # type: ignore[untyped-decorator]
    name="clos.execute_supervisor_run",
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_jitter=True,
    max_retries=3,
)
def execute_supervisor_run_task(tenant_id: str, run_id: str, message: str) -> dict[str, object]:
    """Run one tenant-scoped graph; redelivery resumes from its PostgreSQL checkpoint."""
    return asyncio.run(_execute(UUID(tenant_id), UUID(run_id), message))


@celery_app.task(  # type: ignore[untyped-decorator]
    name="clos.resume_supervisor_run",
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_jitter=True,
    max_retries=3,
)
def resume_supervisor_run_task(
    tenant_id: str, run_id: str, decision: dict[str, object]
) -> dict[str, object]:
    """Resume only the checkpoint addressed by the tenant/run pair."""
    return asyncio.run(_resume(UUID(tenant_id), UUID(run_id), decision))


@celery_app.task(  # type: ignore[untyped-decorator]
    name="clos.expire_approval_request",
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_jitter=True,
    max_retries=3,
)
def expire_approval_request_task(tenant_id: str, approval_id: str) -> int:
    """Expire overdue requests and resume their graphs with rejection decisions."""
    return asyncio.run(_expire_approvals(UUID(tenant_id), UUID(approval_id)))
