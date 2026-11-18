"""Authentication and integration API key routes."""

from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Request, Response, status
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from clos.adapters.db.auth_repository import SqlAlchemyAuthRepository
from clos.adapters.db.session import make_session_factory
from clos.adapters.security.crypto import Argon2PasswordHasher, JwtTokenIssuer
from clos.application.auth import (
    AuthService,
    AuthenticationError,
    AuthorizationError,
    Principal,
    TokenPair,
)
from clos.config import settings

router = APIRouter(prefix="/v1", tags=["authentication"])


class LoginBody(BaseModel):
    tenant_slug: str = Field(min_length=1, max_length=80)
    email: EmailStr
    password: str = Field(min_length=12, max_length=1024)


class RefreshBody(BaseModel):
    refresh_token: str = Field(min_length=1)


class ApiKeyBody(BaseModel):
    label: str = Field(min_length=1, max_length=120)
    permissions: list[str] = Field(min_length=1)
    expires_at: datetime | None = None


class TokenPairBody(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class CurrentUserBody(BaseModel):
    user_id: UUID
    tenant_id: UUID
    email: EmailStr
    role: str


class CreatedApiKeyBody(BaseModel):
    key_id: UUID
    api_key: str
    label: str
    permissions: list[str]


async def get_session(request: Request) -> AsyncIterator[AsyncSession]:
    factory: async_sessionmaker[AsyncSession] | None = getattr(
        request.app.state, "session_factory", None
    )
    if factory is None:
        if settings.database_url is None:
            raise HTTPException(status_code=503, detail="Database is not configured")
        factory = make_session_factory(settings.database_url)
        request.app.state.session_factory = factory
    async with factory() as session, session.begin():
        yield session


def get_auth_service(session: AsyncSession = Depends(get_session)) -> AuthService:
    if settings.auth_jwt_secret is None:
        raise HTTPException(status_code=503, detail="Authentication is not configured")
    issuer = JwtTokenIssuer(settings.auth_jwt_secret.get_secret_value())
    return AuthService(
        SqlAlchemyAuthRepository(session),
        Argon2PasswordHasher(),
        issuer,
        access_token_seconds=settings.access_token_seconds,
        refresh_token_days=settings.refresh_token_days,
    )


async def get_principal(
    authorization: str | None = Header(default=None),
    service: AuthService = Depends(get_auth_service),
) -> Principal:
    if authorization is None or not authorization.lower().startswith("bearer "):
        raise AuthenticationError("Missing bearer credentials")
    token = authorization[7:].strip()
    if token.startswith("clos."):
        return await service.authenticate_api_key(token)
    return await service.authenticate_access_token(token)


@router.post("/auth/token", response_model=TokenPairBody)
async def login(body: LoginBody, service: AuthService = Depends(get_auth_service)) -> TokenPair:
    return await service.login(body.tenant_slug, str(body.email), body.password)


@router.post("/auth/refresh", response_model=TokenPairBody)
async def refresh(
    body: RefreshBody, service: AuthService = Depends(get_auth_service)
) -> TokenPair:
    return await service.refresh(body.refresh_token)


@router.get("/auth/me", response_model=CurrentUserBody)
async def current_user(principal: Principal = Depends(get_principal)) -> CurrentUserBody:
    return CurrentUserBody(
        user_id=principal.user_id,
        tenant_id=principal.tenant_id,
        email=principal.email,
        role=principal.role.value,
    )


@router.post(
    "/integration-api-keys",
    response_model=CreatedApiKeyBody,
    status_code=status.HTTP_201_CREATED,
)
async def create_api_key(
    body: ApiKeyBody,
    idempotency_key: str = Header(alias="Idempotency-Key", min_length=1, max_length=200),
    principal: Principal = Depends(get_principal),
    service: AuthService = Depends(get_auth_service),
) -> CreatedApiKeyBody:
    try:
        key_id, raw_key = await service.create_api_key(
            principal, body.label, body.permissions, body.expires_at, idempotency_key
        )
    except AuthorizationError:
        raise
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return CreatedApiKeyBody(
        key_id=key_id,
        api_key=raw_key,
        label=body.label,
        permissions=body.permissions,
    )


@router.delete("/integration-api-keys/{key_id}", status_code=status.HTTP_204_NO_CONTENT)
async def revoke_api_key(
    key_id: UUID,
    idempotency_key: str = Header(alias="Idempotency-Key", min_length=1, max_length=200),
    principal: Principal = Depends(get_principal),
    service: AuthService = Depends(get_auth_service),
) -> Response:
    del idempotency_key  # Revoke is naturally idempotent for an existing key.
    if not await service.revoke_api_key(principal, key_id):
        raise HTTPException(status_code=404, detail="API key not found")
    return Response(status_code=status.HTTP_204_NO_CONTENT)



