"""Approval use-case permission, expiry configuration, and resume behavior."""

import asyncio
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest

from clos.adapters.notifications import FakeChannelNotifier
from clos.application.approvals import (
    ApprovalConfigurationError,
    ApprovalItem,
    ApprovalService,
    ApprovalStatus,
    Decision,
)
from clos.application.auth import AuthorizationError, Principal
from clos.domain.identity import Role


class FakeWorkflow:
    def __init__(self) -> None:
        self.items: dict[object, ApprovalItem] = {}
        self.created_key = ""

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
        self.created_key = idempotency_key
        item = ApprovalItem(
            uuid4(),
            tenant_id,
            run_id,
            action,
            "write_high",
            "pending",
            {**context, "tool_input": tool_input},
            expires_at,
            datetime.now(UTC),
            None,
            None,
        )
        self.items[item.approval_id] = item
        return item

    async def list_requests(
        self,
        _tenant_id: UUID,
        *,
        status: ApprovalStatus | None,
        cursor: UUID | None,
        limit: int,
    ) -> tuple[list[ApprovalItem], UUID | None]:
        del status, cursor, limit
        return list(self.items.values()), None

    async def decide(
        self,
        tenant_id: UUID,
        approval_id: UUID,
        actor_id: UUID,
        decision: Decision,
        idempotency_key: str,
        tool_input: dict[str, object] | None = None,
    ) -> ApprovalItem:
        item = self.items[approval_id]
        context = dict(item.context)
        if tool_input is not None:
            context["tool_input"] = tool_input
            context["diff"] = {"before": item.context["tool_input"], "after": tool_input}
        context["decision_idempotency_key"] = idempotency_key
        decided = ApprovalItem(
            item.approval_id,
            tenant_id,
            item.run_id,
            item.action,
            item.risk_level,
            decision,
            context,
            item.expires_at,
            item.created_at,
            datetime.now(UTC),
            actor_id,
        )
        self.items[item.approval_id] = decided
        return decided

    async def expire_pending(self, _tenant_id: UUID) -> list[ApprovalItem]:
        return []


class FakeResumer:
    def __init__(self) -> None:
        self.resumed: list[ApprovalItem] = []

    async def resume(self, item: ApprovalItem) -> None:
        self.resumed.append(item)


def _principal(role: Role) -> Principal:
    return Principal(uuid4(), uuid4(), role, "approver@example.test")


def test_approval_request_needs_explicit_expiry_configuration() -> None:
    async def scenario() -> None:
        workflow, notifier = FakeWorkflow(), FakeChannelNotifier("dashboard")
        service = ApprovalService(workflow, notifier)
        with pytest.raises(ApprovalConfigurationError, match="APPROVAL_EXPIRY_SECONDS"):
            await service.request_tool_approval(
                uuid4(), uuid4(), "write_price", {"price": 50}, idempotency_key="req-1"
            )
        assert workflow.items == {}

    asyncio.run(scenario())


def test_approval_modify_and_approve_audits_notification_and_resumes() -> None:
    async def scenario() -> None:
        workflow = FakeWorkflow()
        notifier = FakeChannelNotifier("dashboard")
        resumer = FakeResumer()
        service = ApprovalService(workflow, notifier, expiry_seconds=300, resumer=resumer)
        tenant_id, run_id = uuid4(), uuid4()
        item = await service.request_tool_approval(
            tenant_id,
            run_id,
            "write_price",
            {"price": 40},
            context={"explanation": "keeps configured margin"},
            idempotency_key="tool-call-1",
        )
        assert item.expires_at > datetime.now(UTC) + timedelta(seconds=250)
        assert notifier.records[0].event_type == "approval_requested"

        approver = Principal(uuid4(), tenant_id, Role.MANAGER, "manager@example.test")
        modified = await service.decide(
            approver,
            item.approval_id,
            "approved",
            "decision-1",
            {"price": 43},
        )
        assert modified.context["tool_input"] == {"price": 43}
        assert modified.context["diff"] == {
            "before": {"price": 40},
            "after": {"price": 43},
        }
        assert notifier.records[-1].event_type == "approval_decided"
        assert resumer.resumed == [modified]

    asyncio.run(scenario())


def test_viewer_cannot_list_or_decide_approvals() -> None:
    async def scenario() -> None:
        service = ApprovalService(FakeWorkflow(), FakeChannelNotifier("dashboard"))
        viewer = _principal(Role.VIEWER)
        with pytest.raises(AuthorizationError, match="Approval permission"):
            await service.list_requests(viewer, status=None, cursor=None, limit=20)
        with pytest.raises(AuthorizationError, match="Approval permission"):
            await service.decide(viewer, uuid4(), "rejected", "decision-1")

    asyncio.run(scenario())
