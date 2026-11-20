"""Merchant memory endpoints; tenant identity always comes from authentication."""

from collections.abc import AsyncIterator
from typing import Annotated, Literal
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from pydantic import BaseModel, Field

from clos.adapters.db.memory import MemoryConflict, MemoryRepository
from clos.adapters.memory_runtime import memory_runtime
from clos.agents.common import AgentContext
from clos.agents.support import SupportAgent
from clos.application.auth import AuthorizationError, Principal
from clos.apps.api.auth_routes import get_principal
from clos.apps.api.memory_metrics import empty_results, retrieval_seconds
from clos.domain.identity import role_allows

router = APIRouter(prefix="/v1", tags=["memory"])
Key = Annotated[str, Header(alias="Idempotency-Key", min_length=1, max_length=200)]


class Upload(BaseModel):
    source: str = Field(min_length=1, max_length=200)
    text: str = Field(min_length=1, max_length=200000)
    customer_id: UUID | None = None


class Query(BaseModel):
    query: str = Field(min_length=1, max_length=4000)


class MessageBody(BaseModel):
    text: str = Field(min_length=1, max_length=4000)
    direction: Literal["inbound", "outbound"]


class JobBody(BaseModel):
    run_id: UUID
    status: str


def authorize(principal: Principal = Depends(get_principal)) -> Principal:
    if not role_allows(principal.role, "manage_memory") or not principal.allows("manage_memory"):
        raise AuthorizationError("Memory management permission required")
    return principal


async def get_memory(request: Request) -> AsyncIterator[MemoryRepository]:
    sessions = getattr(request.app.state, "session_factory", None)
    if sessions is None:
        raise HTTPException(503, "Database unavailable")
    async with memory_runtime(sessions) as repository:
        try:
            yield repository
        except MemoryConflict as exc:
            raise HTTPException(409, str(exc)) from exc
        except LookupError as exc:
            raise HTTPException(404, str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc


Auth = Annotated[Principal, Depends(authorize)]
Repo = Annotated[MemoryRepository, Depends(get_memory)]


@router.post("/memory/documents", status_code=202, operation_id="ingestMemoryDocument")
async def ingest(body: Upload, key: Key, principal: Auth, repo: Repo) -> JobBody:
    job = await repo.submit(
        principal.tenant_id,
        principal.user_id,
        key,
        body.customer_id,
        source=body.source,
        body=body.text,
    )
    return JobBody(run_id=job.id, status=job.status)


@router.get("/memory/jobs/{run_id}", operation_id="getMemoryJob")
async def job_status(run_id: UUID, principal: Auth, repo: Repo) -> JobBody:
    job = await repo.job(principal.tenant_id, run_id)
    return JobBody(run_id=job.id, status=job.status)


@router.get("/customers/{customer_id}/memory", operation_id="exportCustomerMemory")
async def export(customer_id: UUID, principal: Auth, repo: Repo) -> dict[str, list[dict[str, str]]]:
    return await repo.export(principal.tenant_id, customer_id, principal.user_id)


@router.delete("/customers/{customer_id}/memory", status_code=202, operation_id="eraseCustomerMemory")
async def erase(customer_id: UUID, key: Key, principal: Auth, repo: Repo) -> JobBody:
    job = await repo.submit(principal.tenant_id, principal.user_id, key, customer_id)
    return JobBody(run_id=job.id, status=job.status)


@router.post("/customers/{customer_id}/memory/messages", operation_id="appendMemoryMessage")
async def append(
    customer_id: UUID, body: MessageBody, key: Key, principal: Auth, repo: Repo
) -> dict[str, UUID]:
    uid = await repo.append(
        principal.tenant_id, customer_id, principal.user_id, key, body.direction, body.text
    )
    return {"message_id": uid}


@router.post("/customers/{customer_id}/memory/search", operation_id="searchCustomerMemory")
async def search(customer_id: UUID, body: Query, principal: Auth, repo: Repo) -> dict[str, object]:
    context = AgentContext(principal.tenant_id, uuid4(), customer_id)
    history = await repo.context(context.tenant_id, customer_id)
    query = " ".join(filter(None, [body.query, history[-500:]]))
    with retrieval_seconds.time():
        answer = await SupportAgent(repo).answer_customer(query, context)
    if not answer["evidence"]:
        empty_results.inc()
    return answer
