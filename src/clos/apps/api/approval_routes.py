"""Tenant-scoped human approval endpoints and dashboard SSE stream."""

import asyncio
import json
from collections.abc import AsyncIterator
from datetime import datetime
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from clos.adapters.db.approvals import SQLApprovalWorkflow
from clos.adapters.db.session import make_session_factory
from clos.adapters.notifications import AuditStreamNotifier
from clos.application.approvals import (
    ApprovalConflict,
    ApprovalItem,
    ApprovalNotFound,
    ApprovalService,
    ApprovalStatus,
    Decision,
)
from clos.application.auth import Principal
from clos.apps.api.auth_routes import get_principal
from clos.apps.worker.main import celery_app
from clos.config import settings

router = APIRouter(prefix="/v1/approvals", tags=["approvals"])


class ApprovalBody(BaseModel):
    approval_id: UUID
    run_id: UUID
    action: str
    risk_level: Literal["write_high"]
    status: ApprovalStatus
    context: dict[str, object]
    expires_at: datetime
    created_at: datetime
    decided_at: datetime | None
    decided_by: UUID | None


class ApprovalPageBody(BaseModel):
    items: list[ApprovalBody]
    next_cursor: UUID | None


class ModifyApprovalBody(BaseModel):
    tool_input: dict[str, object] = Field(min_length=1)


def _body(item: ApprovalItem) -> ApprovalBody:
    return ApprovalBody(
        approval_id=item.approval_id,
        run_id=item.run_id,
        action=item.action,
        risk_level="write_high",
        status=item.status,
        context=item.context,
        expires_at=item.expires_at,
        created_at=item.created_at,
        decided_at=item.decided_at,
        decided_by=item.decided_by,
    )


class CeleryApprovalResumer:
    async def resume(self, item: ApprovalItem) -> None:
        tool_input = item.context.get("tool_input", {})
        payload: dict[str, object] = {
            "approval_id": str(item.approval_id),
            "decision": item.status,
        }
        if item.status == "approved":
            payload["tool_input"] = tool_input
        celery_app.send_task(
            "clos.resume_supervisor_run",
            args=[str(item.tenant_id), str(item.run_id), payload],
        )


class CeleryExpiryScheduler:
    async def schedule(self, tenant_id: UUID, approval_id: UUID, delay_seconds: int) -> None:
        celery_app.send_task(
            "clos.expire_approval_request",
            args=[str(tenant_id), str(approval_id)],
            countdown=delay_seconds,
        )


async def get_approval_service(request: Request) -> ApprovalService:
    factory: async_sessionmaker[AsyncSession] | None = getattr(
        request.app.state, "session_factory", None
    )
    if factory is None:
        if settings.database_url is None:
            raise HTTPException(status_code=503, detail="Database is not configured")
        factory = make_session_factory(settings.database_url)
        request.app.state.session_factory = factory
    return ApprovalService(
        SQLApprovalWorkflow(factory),
        AuditStreamNotifier(),
        expiry_seconds=settings.approval_expiry_seconds,
        resumer=CeleryApprovalResumer(),
        expiry_scheduler=CeleryExpiryScheduler(),
    )


@router.get("", response_model=ApprovalPageBody)
async def list_approvals(
    limit: int = Query(default=50, ge=1, le=100),
    cursor: UUID | None = None,
    status: ApprovalStatus | None = None,
    principal: Principal = Depends(get_principal),
    service: ApprovalService = Depends(get_approval_service),
) -> ApprovalPageBody:
    try:
        items, next_cursor = await service.list_requests(
            principal, status=status, cursor=cursor, limit=limit
        )
    except ApprovalNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return ApprovalPageBody(items=[_body(item) for item in items], next_cursor=next_cursor)


@router.post("/{approval_id}/approve", response_model=ApprovalBody)
async def approve_approval(
    approval_id: UUID,
    idempotency_key: str = Header(alias="Idempotency-Key", min_length=1, max_length=200),
    principal: Principal = Depends(get_principal),
    service: ApprovalService = Depends(get_approval_service),
) -> ApprovalBody:
    return await _decide(service, principal, approval_id, "approved", idempotency_key)


@router.post("/{approval_id}/reject", response_model=ApprovalBody)
async def reject_approval(
    approval_id: UUID,
    idempotency_key: str = Header(alias="Idempotency-Key", min_length=1, max_length=200),
    principal: Principal = Depends(get_principal),
    service: ApprovalService = Depends(get_approval_service),
) -> ApprovalBody:
    return await _decide(service, principal, approval_id, "rejected", idempotency_key)


@router.patch("/{approval_id}", response_model=ApprovalBody)
async def modify_and_approve(
    approval_id: UUID,
    body: ModifyApprovalBody,
    idempotency_key: str = Header(alias="Idempotency-Key", min_length=1, max_length=200),
    principal: Principal = Depends(get_principal),
    service: ApprovalService = Depends(get_approval_service),
) -> ApprovalBody:
    return await _decide(
        service, principal, approval_id, "approved", idempotency_key, body.tool_input
    )


async def _decide(
    service: ApprovalService,
    principal: Principal,
    approval_id: UUID,
    decision: Decision,
    idempotency_key: str,
    tool_input: dict[str, object] | None = None,
) -> ApprovalBody:
    try:
        item = await service.decide(principal, approval_id, decision, idempotency_key, tool_input)
    except ApprovalNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ApprovalConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return _body(item)


@router.get("/events")
async def approval_events(
    request: Request,
    last_event_id: UUID | None = Header(default=None, alias="Last-Event-ID"),
    principal: Principal = Depends(get_principal),
) -> StreamingResponse:
    if not principal.allows("manage_approvals"):
        raise HTTPException(status_code=403, detail="Approval permission denied")
    factory: async_sessionmaker[AsyncSession] | None = getattr(
        request.app.state, "session_factory", None
    )
    if factory is None:
        if settings.database_url is None:
            raise HTTPException(status_code=503, detail="Database is not configured")
        factory = make_session_factory(settings.database_url)

    async def stream() -> AsyncIterator[str]:
        cursor = last_event_id
        workflow = SQLApprovalWorkflow(factory)
        while not await request.is_disconnected():
            events = await workflow.list_approval_events(principal.tenant_id, cursor)
            for event in events:
                event_id = event["event_id"]
                cursor = event_id if isinstance(event_id, UUID) else cursor
                payload = json.dumps(event, default=str, separators=(",", ":"))
                yield f"id: {event_id}\nevent: {event['event_type']}\ndata: {payload}\n\n"
            if not events:
                yield ": keep-alive\n\n"
            await asyncio.sleep(1)

    return StreamingResponse(
        stream(), media_type="text/event-stream", headers={"Cache-Control": "no-cache"}
    )
