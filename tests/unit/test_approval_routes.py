"""Approval HTTP contract and role checks using in-memory workflow fakes."""

from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from fastapi.testclient import TestClient

from clos.adapters.notifications import FakeChannelNotifier
from clos.application.approvals import (
    ApprovalItem,
    ApprovalService,
    ApprovalStatus,
    Decision,
)
from clos.application.auth import Principal
from clos.apps.api.approval_routes import get_approval_service
from clos.apps.api.auth_routes import get_principal
from clos.apps.api.main import app
from clos.domain.identity import Role


class RouteWorkflow:
    def __init__(self, tenant_id: UUID) -> None:
        self.tenant_id = tenant_id
        now = datetime.now(UTC)
        self.item = ApprovalItem(
            uuid4(),
            tenant_id,
            uuid4(),
            "apply_price_change",
            "write_high",
            "pending",
            {"tool_input": {"price": 12}, "diff": {"before": 10, "after": 12}},
            now + timedelta(minutes=2),
            now,
            None,
            None,
        )

    async def create_request(self, *args: object, **kwargs: object) -> ApprovalItem:
        del args, kwargs
        return self.item

    async def list_requests(
        self,
        tenant_id: UUID,
        *,
        status: ApprovalStatus | None,
        cursor: UUID | None,
        limit: int,
    ) -> tuple[list[ApprovalItem], UUID | None]:
        del status, cursor, limit
        return ([self.item] if tenant_id == self.tenant_id else []), None

    async def decide(
        self,
        tenant_id: UUID,
        approval_id: UUID,
        actor_id: UUID,
        decision: Decision,
        idempotency_key: str,
        tool_input: dict[str, object] | None = None,
    ) -> ApprovalItem:
        del idempotency_key
        assert approval_id == self.item.approval_id
        context = dict(self.item.context)
        if tool_input is not None:
            context["tool_input"] = tool_input
        self.item = ApprovalItem(
            self.item.approval_id,
            tenant_id,
            self.item.run_id,
            self.item.action,
            self.item.risk_level,
            decision,
            context,
            self.item.expires_at,
            self.item.created_at,
            datetime.now(UTC),
            actor_id,
        )
        return self.item

    async def expire_pending(self, _tenant_id: UUID) -> list[ApprovalItem]:
        return []


def test_approval_endpoints_list_modify_and_approve_for_authorized_role() -> None:
    tenant_id = uuid4()
    principal = Principal(uuid4(), tenant_id, Role.MANAGER, "manager@example.test")
    workflow = RouteWorkflow(tenant_id)
    service = ApprovalService(workflow, FakeChannelNotifier("dashboard"), expiry_seconds=60)
    app.dependency_overrides[get_principal] = lambda: principal
    app.dependency_overrides[get_approval_service] = lambda: service
    try:
        with TestClient(app) as client:
            page = client.get("/v1/approvals")
            assert page.status_code == 200
            assert page.json()["items"][0]["approval_id"] == str(workflow.item.approval_id)

            response = client.patch(
                f"/v1/approvals/{workflow.item.approval_id}",
                headers={"Idempotency-Key": "modify-1"},
                json={"tool_input": {"price": 11}},
            )
            assert response.status_code == 200
            assert response.json()["status"] == "approved"
            assert response.json()["context"]["tool_input"] == {"price": 11}
    finally:
        app.dependency_overrides.clear()


def test_approval_endpoints_reject_viewer_with_problem_json() -> None:
    principal = Principal(uuid4(), uuid4(), Role.VIEWER, "viewer@example.test")
    workflow = RouteWorkflow(principal.tenant_id)
    app.dependency_overrides[get_principal] = lambda: principal
    app.dependency_overrides[get_approval_service] = lambda: ApprovalService(
        workflow, FakeChannelNotifier("dashboard"), expiry_seconds=60
    )
    try:
        with TestClient(app) as client:
            response = client.get("/v1/approvals")
            assert response.status_code == 403
            assert response.headers["content-type"].startswith("application/problem+json")
            assert response.json()["code"] == "FORBIDDEN"
    finally:
        app.dependency_overrides.clear()
