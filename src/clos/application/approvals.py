"""Use cases and ports for safe, tenant-scoped human approval workflows."""

from dataclasses import dataclass
from datetime import datetime
from typing import Literal, Protocol
from uuid import UUID

from clos.application.auth import AuthorizationError, Principal

ApprovalStatus = Literal["pending", "approved", "rejected"]
Decision = Literal["approved", "rejected"]


@dataclass(frozen=True, slots=True)
class ApprovalItem:
    approval_id: UUID
    tenant_id: UUID
    run_id: UUID
    action: str
    risk_level: str
    status: ApprovalStatus
    context: dict[str, object]
    expires_at: datetime
    created_at: datetime
    decided_at: datetime | None
    decided_by: UUID | None


class ApprovalWorkflowPort(Protocol):
    async def create_request(
        self,
        tenant_id: UUID,
        run_id: UUID,
        action: str,
        tool_input: dict[str, object],
        context: dict[str, object],
        idempotency_key: str,
        expires_at: datetime,
    ) -> ApprovalItem: ...

    async def list_requests(
        self,
        tenant_id: UUID,
        *,
        status: ApprovalStatus | None,
        cursor: UUID | None,
        limit: int,
    ) -> tuple[list[ApprovalItem], UUID | None]: ...

    async def decide(
        self,
        tenant_id: UUID,
        approval_id: UUID,
        actor_id: UUID,
        decision: Decision,
        idempotency_key: str,
        tool_input: dict[str, object] | None = None,
    ) -> ApprovalItem: ...

    async def expire_pending(self, tenant_id: UUID) -> list[ApprovalItem]: ...


class ApprovalNotificationPort(Protocol):
    async def publish(self, event_type: str, item: ApprovalItem) -> None: ...


class ApprovalResumePort(Protocol):
    async def resume(self, item: ApprovalItem) -> None: ...


class ApprovalExpirySchedulerPort(Protocol):
    async def schedule(self, tenant_id: UUID, approval_id: UUID, delay_seconds: int) -> None: ...


class ApprovalNotFound(LookupError):
    """Approval request is missing from the authenticated tenant."""


class ApprovalConflict(RuntimeError):
    """Approval is expired, already decided, or reused inconsistently."""

    def __init__(self, message: str, *, expired_item: ApprovalItem | None = None) -> None:
        super().__init__(message)
        self.expired_item = expired_item


class ApprovalConfigurationError(RuntimeError):
    """Required approval expiry configuration has not been supplied."""


class ApprovalService:
    def __init__(
        self,
        workflow: ApprovalWorkflowPort,
        notifications: ApprovalNotificationPort,
        *,
        expiry_seconds: int | None = None,
        resumer: ApprovalResumePort | None = None,
        expiry_scheduler: ApprovalExpirySchedulerPort | None = None,
    ) -> None:
        if expiry_seconds is not None and expiry_seconds < 1:
            raise ValueError("Approval expiry must be at least one second")
        self._workflow = workflow
        self._notifications = notifications
        self.expiry_seconds = expiry_seconds
        self._resumer = resumer
        self._expiry_scheduler = expiry_scheduler

    async def request_tool_approval(
        self,
        tenant_id: UUID,
        run_id: UUID,
        tool_name: str,
        tool_input: dict[str, object],
        *,
        context: dict[str, object] | None = None,
        idempotency_key: str,
    ) -> ApprovalItem:
        from datetime import UTC, datetime, timedelta

        if self.expiry_seconds is None:
            raise ApprovalConfigurationError(
                "APPROVAL_EXPIRY_SECONDS must be configured before write_high actions are enabled"
            )

        item = await self._workflow.create_request(
            tenant_id,
            run_id,
            tool_name,
            tool_input,
            context or {},
            idempotency_key,
            datetime.now(UTC) + timedelta(seconds=self.expiry_seconds),
        )
        await self._notifications.publish("approval_requested", item)
        if self._expiry_scheduler is not None:
            await self._expiry_scheduler.schedule(tenant_id, item.approval_id, self.expiry_seconds)
        return item

    async def list_requests(
        self,
        principal: Principal,
        *,
        status: ApprovalStatus | None,
        cursor: UUID | None,
        limit: int,
    ) -> tuple[list[ApprovalItem], UUID | None]:
        self._require_approval_permission(principal)
        expired = await self._workflow.expire_pending(principal.tenant_id)
        for item in expired:
            await self._notifications.publish("approval_expired", item)
            if self._resumer is not None:
                await self._resumer.resume(item)
        return await self._workflow.list_requests(
            principal.tenant_id, status=status, cursor=cursor, limit=limit
        )

    async def decide(
        self,
        principal: Principal,
        approval_id: UUID,
        decision: Decision,
        idempotency_key: str,
        tool_input: dict[str, object] | None = None,
    ) -> ApprovalItem:
        self._require_approval_permission(principal)
        try:
            item = await self._workflow.decide(
                principal.tenant_id,
                approval_id,
                principal.user_id,
                decision,
                idempotency_key,
                tool_input,
            )
        except ApprovalConflict as conflict:
            if conflict.expired_item is not None:
                await self._notifications.publish("approval_expired", conflict.expired_item)
                if self._resumer is not None:
                    await self._resumer.resume(conflict.expired_item)
            else:
                await self.expire_due(principal.tenant_id)
            raise
        await self._notifications.publish("approval_decided", item)
        if self._resumer is not None:
            await self._resumer.resume(item)
        return item

    async def expire_due(self, tenant_id: UUID) -> list[ApprovalItem]:
        items = await self._workflow.expire_pending(tenant_id)
        for item in items:
            await self._notifications.publish("approval_expired", item)
            if self._resumer is not None:
                await self._resumer.resume(item)
        return items

    @staticmethod
    def _require_approval_permission(principal: Principal) -> None:
        if not principal.allows("manage_approvals"):
            raise AuthorizationError("Approval permission denied")
