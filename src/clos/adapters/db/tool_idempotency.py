"""Durable tenant-scoped idempotency records for tool execution."""

import json
from collections.abc import Awaitable, Callable
from uuid import UUID

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from clos.adapters.db.models import ApprovalRequest, ToolCall
from clos.adapters.db.session import tenant_session
from clos.agents.tools import IdempotencyPort, ToolIdempotencyConflict
from clos.domain.identity import RiskLevel


class SQLToolIdempotencyStore(IdempotencyPort):
    """Serialize same-key execution in PostgreSQL and persist the JSON result."""

    def __init__(self, sessions: async_sessionmaker[AsyncSession]) -> None:
        self._sessions = sessions

    async def run_once(
        self,
        key: str,
        action: Callable[[], Awaitable[object]],
        *,
        risk_level: RiskLevel,
        input_data: dict[str, object],
    ) -> object:
        tenant_text, run_text, tool_name, request_key = key.split(":", maxsplit=3)
        tenant_id, run_id = UUID(tenant_text), UUID(run_text)
        failure: Exception | None = None
        result: object = None
        async with tenant_session(self._sessions, tenant_id) as session:
            await session.execute(
                text("SELECT pg_advisory_xact_lock(hashtextextended(:key, 0))"),
                {"key": key},
            )
            query = await session.execute(
                select(ToolCall).where(
                    ToolCall.tenant_id == tenant_id,
                    ToolCall.agent_run_id == run_id,
                    ToolCall.tool_name == tool_name,
                    ToolCall.idempotency_key == request_key,
                )
            )
            record = query.scalar_one_or_none()
            if record is not None and record.input_data != input_data:
                raise ToolIdempotencyConflict("Idempotency key reused with different input")
            if record is not None and record.status == "completed" and record.output_data:
                return record.output_data["value"]
            if record is None:
                record = ToolCall(
                    tenant_id=tenant_id,
                    agent_run_id=run_id,
                    tool_name=tool_name,
                    status="running",
                    risk_level=risk_level.value,
                    idempotency_key=request_key,
                    input_data=input_data,
                )
                session.add(record)
                await session.flush()
            else:
                record.status = "running"
                record.risk_level = risk_level.value
                record.input_data = input_data
                record.output_data = None
            try:
                result = await action()
                serializable = json.loads(json.dumps(result, allow_nan=False))
                record.output_data = {"value": serializable}
                record.status = "completed"
            except Exception as exc:
                record.output_data = {"error_type": type(exc).__name__}
                record.status = "failed"
                failure = exc
        if failure is not None:
            raise failure
        return result


class SQLApprovalVerifier:
    """Verify a high-risk tool against an explicitly approved tenant-scoped request."""

    def __init__(self, sessions: async_sessionmaker[AsyncSession]) -> None:
        self._sessions = sessions

    async def is_approved(
        self, tenant_id: UUID, run_id: UUID, approval_id: UUID, tool_name: str
    ) -> bool:
        async with tenant_session(self._sessions, tenant_id) as session:
            result = await session.execute(
                select(ApprovalRequest.id).where(
                    ApprovalRequest.id == approval_id,
                    ApprovalRequest.tenant_id == tenant_id,
                    ApprovalRequest.agent_run_id == run_id,
                    ApprovalRequest.action == tool_name,
                    ApprovalRequest.status == "approved",
                )
            )
            return result.scalar_one_or_none() is not None
