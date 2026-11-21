"""Run admission, resumable events, approvals socket and verified integration ingress."""
import asyncio
import json
import time
from collections.abc import AsyncIterator
from typing import Annotated, Any, Literal
from uuid import UUID

from fastapi import APIRouter,Depends,Header,HTTPException,Query,Request,Response,WebSocket,WebSocketDisconnect
from fastapi.encoders import jsonable_encoder
from fastapi.responses import StreamingResponse
from pydantic import BaseModel,Field,ValidationError
from redis.exceptions import RedisError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession,async_sessionmaker

from clos.adapters.db.approvals import SQLApprovalWorkflow
from clos.adapters.db.delivery import Journal,enqueue,replay,submit_run
from clos.adapters.delivery_control import DeliveryPaused,check_active
from clos.adapters.db.models import AgentRun,AsyncJob,Tenant
from clos.adapters.db.session import tenant_session
from clos.application.approvals import ApprovalNotFound
from clos.application.auth import AuthenticationError,Principal
from clos.application.delivery import JobConflict,verified
from clos.application.integration_events import OrderCreated,TrackingUpdate
from clos.apps.api.auth_routes import authenticate,get_auth_service,get_principal
from clos.apps.api.limits import enforce
from clos.config import settings
from clos.domain.identity import role_allows

router=APIRouter(prefix="/v1",tags=["delivery"])
Key=Annotated[str,Header(alias="Idempotency-Key",min_length=1,max_length=200)]
Auth=Annotated[Principal,Depends(get_principal)]


class RunBody(BaseModel):
    message: str=Field(min_length=1,max_length=8000)


def require(principal: Principal,permission: str) -> None:
    if not role_allows(principal.role,permission) or not principal.allows(permission):
        raise HTTPException(403,"Insufficient permission")


def factory(request: Request) -> async_sessionmaker[AsyncSession]:
    sessions: async_sessionmaker[AsyncSession] | None=getattr(request.app.state,"session_factory",None)
    if sessions is None:
        raise HTTPException(503,"Database unavailable")
    return sessions


@router.post("/runs",operation_id="createRun",status_code=202)
async def create(body: RunBody,key: Key,principal: Auth,request: Request,response: Response) -> dict[str,UUID]:
    require(principal,"run_agents")
    if not body.message.strip():
        raise HTTPException(422,"Message cannot be blank")
    try:
        await check_active(principal.tenant_id)
        async with tenant_session(factory(request),principal.tenant_id) as db:
            tenant=await db.get(Tenant,principal.tenant_id)
            if not tenant or not tenant.is_active:
                raise HTTPException(403,"Tenant inactive")
            uid=await submit_run(db,principal.tenant_id,key,body.message,principal.user_id)
    except (DeliveryPaused,RedisError) as exc:
        raise HTTPException(503,"Run admission unavailable") from exc
    except JobConflict as exc:
        raise HTTPException(409,str(exc)) from exc
    response.headers["Location"]=f"/v1/runs/{uid}"
    return {"run_id":uid}


@router.get("/runs/{run_id}",operation_id="getRun")
async def status(run_id: UUID,principal: Auth,request: Request) -> dict[str,Any]:
    require(principal,"read")
    async with tenant_session(factory(request),principal.tenant_id) as db:
        run=await db.get(AgentRun,run_id)
        if not run:
            raise HTTPException(404,"Run not found")
        return {"run_id":run.id,"status":run.status,"response":(run.explanation or {}).get("response")}


@router.get("/runs/{run_id}/events",operation_id="streamRunEvents")
async def stream(run_id: UUID,principal: Auth,request: Request,
        last: UUID | None=Header(None,alias="Last-Event-ID")) -> StreamingResponse:
    require(principal,"read")
    journal=Journal(factory(request),principal.tenant_id,run_id)
    try:
        start=await journal.cursor(last)
    except LookupError as exc:
        raise HTTPException(404,str(exc)) from exc

    async def frames() -> AsyncIterator[str]:
        cursor=start
        while not await request.is_disconnected():
            rows,state=await journal.page(cursor)
            for row in rows:
                cursor=row.position
                data=json.dumps({"event_id":str(row.id),"event_type":row.event_type,"run_id":str(run_id),
                    "occurred_at":row.created_at.isoformat(),"data":row.data},separators=(",",":"))
                yield f"id: {row.id}\nevent: {row.event_type}\ndata: {data}\n\n"
            if len(rows)<100 and state in {"completed","failed","budget_exceeded","awaiting_approval"}:
                break
            if not rows:
                yield ": keep-alive\n\n"
                await asyncio.sleep(1)
    return StreamingResponse(frames(),media_type="text/event-stream",
             headers={"Cache-Control":"no-store","X-Accel-Buffering":"no"})


@router.get("/dead-letters",operation_id="listDeadLetters")
async def letters(principal: Auth,request: Request,cursor: UUID | None=None,
                  limit: int=Query(50,ge=1,le=100)) -> dict[str,Any]:
    require(principal,"manage_delivery")
    stmt=select(AsyncJob).where(AsyncJob.tenant_id==principal.tenant_id,AsyncJob.status=="dead")
    if cursor:
        stmt=stmt.where(AsyncJob.id>cursor)
    async with tenant_session(factory(request),principal.tenant_id) as db:
        rows=list(await db.scalars(stmt.order_by(AsyncJob.id).limit(limit+1)))
        return {"items":[{"job_id":row.id,"kind":row.kind,"attempts":row.attempts,
                          "error_code":row.error_code} for row in rows[:limit]],
                "next_cursor":rows[limit-1].id if len(rows)>limit else None}


@router.post("/dead-letters/{job_id}/replays",operation_id="replayDeadLetter",status_code=202)
async def requeue(job_id: UUID,key: Key,principal: Auth,request: Request) -> dict[str,UUID]:
    require(principal,"manage_delivery")
    try:
        async with tenant_session(factory(request),principal.tenant_id) as db:
            await replay(db,principal.tenant_id,job_id,principal.user_id,key)
    except LookupError as exc:
        raise HTTPException(404,str(exc)) from exc
    except JobConflict as exc:
        raise HTTPException(409,str(exc)) from exc
    return {"job_id":job_id}


@router.post("/webhooks/{tenant_id}/{source}",operation_id="receiveIntegrationWebhook",status_code=202)
async def receive(tenant_id: UUID,source: Literal["shopify","carrier"],request: Request) -> dict[str,UUID]:
    binding=settings.integrations.get(tenant_id)
    secret=None if not binding else (binding.shopify_secret if source=="shopify" else binding.carrier_secret)
    if not secret:
        raise HTTPException(401,"Invalid webhook credentials")
    body=bytearray()
    async for block in request.stream():
        if len(body)+len(block)>1_000_000:
            raise HTTPException(413,"Webhook exceeds size limit")
        body.extend(block)
    shopify=source=="shopify"
    event_id=request.headers.get("X-Shopify-Webhook-Id" if shopify else "X-CLOS-Event-Id","")
    supplied=request.headers.get("X-Shopify-Hmac-Sha256" if shopify else "X-CLOS-Signature","")
    if not verified(secret.get_secret_value(),source,supplied,event_id,
            request.headers.get("X-CLOS-Timestamp",""),bytes(body),int(time.time())):
        raise HTTPException(401,"Invalid webhook signature")
    if shopify and request.headers.get("X-Shopify-Topic")!="orders/create":
        raise HTTPException(422,"Unsupported Shopify topic")
    await enforce(request,tenant_id,source)
    try:
        if shopify:
            order=OrderCreated.model_validate_json(body)
            payload=order.model_dump(mode="json")
            key=str(order.id)
        else:
            payload=TrackingUpdate.model_validate_json(body).model_dump(mode="json")
            key=event_id
        async with tenant_session(factory(request),tenant_id) as db:
            tenant=await db.get(Tenant,tenant_id)
            if not tenant or not tenant.is_active:
                raise HTTPException(403,"Tenant inactive")
            job,_=await enqueue(db,tenant_id,source,key,payload)
            return {"job_id":job.id}
    except ValidationError as exc:
        raise HTTPException(422,"Invalid integration payload") from exc
    except JobConflict as exc:
        raise HTTPException(409,str(exc)) from exc


@router.websocket("/approvals/ws")
async def approval_socket(socket: WebSocket) -> None:
    sessions: async_sessionmaker[AsyncSession] | None=getattr(socket.app.state,"session_factory",None)
    if sessions is None:
        await socket.close(code=1013)
        return
    await socket.accept()
    try:
        auth=socket.headers.get("Authorization")
        if auth is None:
            auth="Bearer "+await asyncio.wait_for(socket.receive_text(),5)
        cursor_raw=socket.headers.get("Last-Event-ID") or socket.query_params.get("cursor")
        cursor=UUID(cursor_raw) if cursor_raw else None
        workflow=SQLApprovalWorkflow(sessions)
        while True:
            async with sessions.begin() as db:
                principal=await authenticate(auth,get_auth_service(db))
            require(principal,"manage_approvals")
            if not (await socket.app.state.limiter.take(principal.tenant_id,str(principal.user_id))).allowed:
                await socket.close(code=1013)
                return
            # Recheck credentials and both quotas at least once a minute.
            for _ in range(15):
                rows=await workflow.list_approval_events(principal.tenant_id,cursor)
                for row in rows:
                    await socket.send_json(jsonable_encoder(row))
                    cursor=UUID(str(row["event_id"]))
                if not rows:
                    await socket.send_json({"type":"heartbeat"})
                await asyncio.sleep(1)
    except WebSocketDisconnect:
        return
    except (AuthenticationError,HTTPException,ValueError,ApprovalNotFound,TimeoutError):
        await socket.close(code=1008)
    except RedisError:
        await socket.close(code=1013)
