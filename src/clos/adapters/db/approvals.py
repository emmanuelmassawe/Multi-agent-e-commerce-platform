"""PostgreSQL approval persistence, tenant RLS, and audit trail."""

from datetime import UTC, datetime
from typing import cast
from uuid import UUID

from sqlalchemy import select, tuple_
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from clos.adapters.db.models import AgentRun, ApprovalRequest, AuditLog, utc_now
from clos.adapters.db.session import tenant_session
from clos.application.approvals import (
    ApprovalConflict,
    ApprovalItem,
    ApprovalNotFound,
    ApprovalStatus,
    ApprovalWorkflowPort,
    Decision,
)


def _item(row: ApprovalRequest) -> ApprovalItem:
    return ApprovalItem(
        approval_id=row.id,
        tenant_id=row.tenant_id,
        run_id=row.agent_run_id,
        action=row.action,
        risk_level=row.risk_level,
        status=cast(ApprovalStatus, row.status),
        context=dict(row.context),
        expires_at=row.expires_at,
        created_at=row.created_at,
        decided_at=row.decided_at,
        decided_by=row.decided_by,
    )


class SQLApprovalWorkflow(ApprovalWorkflowPort):
    def __init__(self, sessions: async_sessionmaker[AsyncSession]) -> None:
        self._sessions = sessions

    async def get_request(self, tenant_id: UUID, approval_id: UUID) -> ApprovalItem | None:
        async with tenant_session(self._sessions, tenant_id) as session:
            result = await session.execute(
                select(ApprovalRequest).where(
                    ApprovalRequest.id == approval_id,
                    ApprovalRequest.tenant_id == tenant_id,
                )
            )
            row = result.scalar_one_or_none()
            return _item(row) if row is not None else None

    async def create_request(
        self,
        tenant_id: UUID,
        run_id: UUID,
        action: str,
        tool_input: dict[str, object],
        context: dict[str, object],
        idempotency_key: str,
        expires_at: datetime,
    ) -> ApprovalItem:
        async with tenant_session(self._sessions, tenant_id) as session:
            run = await session.execute(
                select(AgentRun.id).where(
                    AgentRun.id == run_id,
                    AgentRun.tenant_id == tenant_id,
                )
            )
            if run.scalar_one_or_none() is None:
                raise ApprovalNotFound("Agent run not found in tenant scope")
            existing = await session.execute(
                select(ApprovalRequest).where(
                    ApprovalRequest.tenant_id == tenant_id,
                    ApprovalRequest.agent_run_id == run_id,
                    ApprovalRequest.action == action,
                    ApprovalRequest.tool_idempotency_key == idempotency_key,
                )
            )
            found = existing.scalar_one_or_none()
            if found is not None:
                if found.context.get("requested_tool_input") != tool_input:
                    raise ApprovalConflict("Approval key reused with different tool input")
                return _item(found)
            payload = {
                **context,
                "requested_tool_input": tool_input,
                "tool_input": tool_input,
                "diff": context.get("diff", {"before": tool_input, "after": tool_input}),
                "explanation": context.get(
                    "explanation", "High-risk action requires human review."
                ),
            }
            row = ApprovalRequest(
                tenant_id=tenant_id,
                agent_run_id=run_id,
                action=action,
                tool_idempotency_key=idempotency_key,
                risk_level="write_high",
                status="pending",
                context=payload,
                expires_at=expires_at,
            )
            session.add(row)
            await session.flush()
            session.add(
                AuditLog(
                    tenant_id=tenant_id,
                    actor_id=None,
                    action="approval_requested",
                    entity_type="approval_request",
                    entity_id=row.id,
                    details={"run_id": str(run_id), "tool": action, "risk_level": "write_high"},
                )
            )
            await session.flush()
            return _item(row)

    async def list_requests(
        self,
        tenant_id: UUID,
        *,
        status: ApprovalStatus | None,
        cursor: UUID | None,
        limit: int,
    ) -> tuple[list[ApprovalItem], UUID | None]:
        async with tenant_session(self._sessions, tenant_id) as session:
            statement = select(ApprovalRequest).where(ApprovalRequest.tenant_id == tenant_id)
            if status is not None:
                statement = statement.where(ApprovalRequest.status == status)
            if cursor is not None:
                cursor_result = await session.execute(
                    select(ApprovalRequest.created_at, ApprovalRequest.id).where(
                        ApprovalRequest.id == cursor,
                        ApprovalRequest.tenant_id == tenant_id,
                    )
                )
                cursor_row = cursor_result.one_or_none()
                if cursor_row is None:
                    raise ApprovalNotFound("Approval cursor not found in tenant scope")
                statement = statement.where(
                    tuple_(ApprovalRequest.created_at, ApprovalRequest.id)
                    < (cursor_row.created_at, cursor_row.id)
                )
            result = await session.execute(
                statement.order_by(
                    ApprovalRequest.created_at.desc(), ApprovalRequest.id.desc()
                ).limit(limit + 1)
            )
            rows = list(result.scalars().all())
            next_cursor = rows[limit - 1].id if len(rows) > limit else None
            return [_item(row) for row in rows[:limit]], next_cursor

    async def is_approved(
        self,
        tenant_id: UUID,
        run_id: UUID,
        approval_id: UUID,
        tool_name: str,
        tool_input: dict[str, object],
    ) -> bool:
        async with tenant_session(self._sessions, tenant_id) as session:
            result = await session.execute(
                select(ApprovalRequest).where(
                    ApprovalRequest.id == approval_id,
                    ApprovalRequest.tenant_id == tenant_id,
                    ApprovalRequest.agent_run_id == run_id,
                    ApprovalRequest.action == tool_name,
                    ApprovalRequest.status == "approved",
                    ApprovalRequest.decided_at <= ApprovalRequest.expires_at,
                )
            )
            row = result.scalar_one_or_none()
            return row is not None and row.context.get("tool_input") == tool_input

    async def list_approval_events(
        self, tenant_id: UUID, cursor: UUID | None, *, limit: int = 100
    ) -> list[dict[str, object]]:
        async with tenant_session(self._sessions, tenant_id) as session:
            statement = select(AuditLog).where(
                AuditLog.tenant_id == tenant_id,
                AuditLog.entity_type == "approval_request",
                AuditLog.action.in_(
                    {
                        "approval_requested",
                        "approval_approved",
                        "approval_rejected",
                        "approval_expired",
                    }
                ),
            )
            if cursor is not None:
                prior_result = await session.execute(
                    select(AuditLog.created_at, AuditLog.id).where(
                        AuditLog.id == cursor, AuditLog.tenant_id == tenant_id
                    )
                )
                prior = prior_result.one_or_none()
                if prior is None:
                    raise ApprovalNotFound("Approval event cursor not found in tenant scope")
                statement = statement.where(
                    tuple_(AuditLog.created_at, AuditLog.id) > (prior.created_at, prior.id)
                )
            result = await session.execute(
                statement.order_by(AuditLog.created_at, AuditLog.id).limit(limit)
            )
            return [
                {
                    "event_id": row.id,
                    "approval_id": row.entity_id,
                    "event_type": (
                        "approval_decided"
                        if row.action in {"approval_approved", "approval_rejected"}
                        else row.action
                    ),
                    "occurred_at": row.created_at,
                    "data": row.details,
                }
                for row in result.scalars().all()
            ]

    async def decide(
        self,
        tenant_id: UUID,
        approval_id: UUID,
        actor_id: UUID,
        decision: Decision,
        idempotency_key: str,
        tool_input: dict[str, object] | None = None,
    ) -> ApprovalItem:
        expired = False
        decided_item: ApprovalItem | None = None
        async with tenant_session(self._sessions, tenant_id) as session:
            result = await session.execute(
                select(ApprovalRequest)
                .where(
                    ApprovalRequest.id == approval_id,
                    ApprovalRequest.tenant_id == tenant_id,
                )
                .with_for_update()
            )
            row = result.scalar_one_or_none()
            if row is None:
                raise ApprovalNotFound("Approval request not found in tenant scope")
            now = utc_now()
            if row.status == "pending" and row.expires_at <= now:
                self._reject_expired(session, row, now)
                await session.flush()
                expired = True
                decided_item = _item(row)
            elif row.status != "pending":
                if (
                    row.status == decision
                    and row.context.get("decision_idempotency_key") == idempotency_key
                    and (tool_input is None or row.context.get("tool_input") == tool_input)
                ):
                    return _item(row)
                raise ApprovalConflict("Approval request is already decided")
            else:
                context = dict(row.context)
                previous_input = context.get("tool_input")
                if tool_input is not None:
                    context["tool_input"] = tool_input
                    context["diff"] = {"before": previous_input, "after": tool_input}
                    decision = "approved"
                context["decision_idempotency_key"] = idempotency_key
                row.context = context
                row.status = decision
                row.decided_by = actor_id
                row.decided_at = now
                session.add(
                    AuditLog(
                        tenant_id=tenant_id,
                        actor_id=actor_id,
                        action=f"approval_{decision}",
                        entity_type="approval_request",
                        entity_id=row.id,
                        details={
                            "run_id": str(row.agent_run_id),
                            "tool": row.action,
                            "status": decision,
                            "idempotency_key": idempotency_key,
                            "modified": tool_input is not None,
                        },
                    )
                )
                await session.flush()
                decided_item = _item(row)
        if expired:
            if decided_item is not None:
                raise ApprovalConflict(
                    "Approval request expired and was rejected", expired_item=decided_item
                )
            raise ApprovalConflict("Approval request expired and was rejected")
        if decided_item is None:
            raise ApprovalConflict("Approval decision was not recorded")
        return decided_item

    async def expire_pending(self, tenant_id: UUID) -> list[ApprovalItem]:
        expired_items: list[ApprovalItem] = []
        async with tenant_session(self._sessions, tenant_id) as session:
            result = await session.execute(
                select(ApprovalRequest)
                .where(
                    ApprovalRequest.tenant_id == tenant_id,
                    ApprovalRequest.status == "pending",
                    ApprovalRequest.expires_at <= datetime.now(UTC),
                )
                .with_for_update(skip_locked=True)
            )
            now = utc_now()
            for row in result.scalars().all():
                self._reject_expired(session, row, now)
                expired_items.append(_item(row))
            await session.flush()
        return expired_items

    @staticmethod
    def _reject_expired(session: AsyncSession, row: ApprovalRequest, now: datetime) -> None:
        row.status = "rejected"
        row.decided_at = now
        context = dict(row.context)
        context["decision_reason"] = "expired"
        row.context = context
        session.add(
            AuditLog(
                tenant_id=row.tenant_id,
                actor_id=None,
                action="approval_expired",
                entity_type="approval_request",
                entity_id=row.id,
                details={"run_id": str(row.agent_run_id), "tool": row.action},
            )
        )
