"""FastAPI application and process health endpoints."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from uuid import uuid4

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, Response
from redis.asyncio import Redis
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from starlette.middleware.base import RequestResponseEndpoint

from clos.adapters.db.session import make_session_factory
from clos.adapters.quota import RedisRateLimit
from clos.application.auth import AuthenticationError, AuthorizationError
from clos.apps.api.approval_routes import router as approval_router
from clos.apps.api.auth_routes import router as auth_router
from clos.apps.api.delivery_routes import router as delivery_router
from clos.apps.api.memory_metrics import router as metrics_router
from clos.apps.api.memory_routes import router as memory_router
from clos.config import settings
from clos.logging import configure_logging

configure_logging(settings.log_level)


@asynccontextmanager
async def lifespan(application: FastAPI) -> AsyncIterator[None]:
    redis = Redis.from_url(settings.redis_url, socket_timeout=2, socket_connect_timeout=2)
    application.state.limiter = RedisRateLimit(
        redis, settings.tenant_requests_per_minute, settings.user_requests_per_minute
    )
    factory: async_sessionmaker[AsyncSession] | None = None
    if settings.database_url is not None:
        factory = make_session_factory(settings.database_url)
        application.state.session_factory = factory
    try:
        yield
    finally:
        await redis.aclose()
        if factory is not None:
            await factory.kw["bind"].dispose()


app = FastAPI(title="CLOS API", version="0.1.0", lifespan=lifespan)
app.include_router(auth_router)
app.include_router(approval_router)
app.include_router(memory_router)
app.include_router(metrics_router)
app.include_router(delivery_router)


@app.middleware("http")
async def response_headers(request: Request, call_next: RequestResponseEndpoint) -> Response:
    request.state.trace_id = str(uuid4())
    response = await call_next(request)
    response.headers.update(getattr(request.state, "rate_headers", {}))
    response.headers["X-Request-ID"] = request.state.trace_id
    response.headers["X-Trace-ID"] = request.state.trace_id
    return response


@app.exception_handler(AuthenticationError)
async def authentication_error_handler(request: Request, exc: AuthenticationError) -> JSONResponse:
    return JSONResponse(
        status_code=401,
        media_type="application/problem+json",
        content={
            "type": "about:blank",
            "title": "Authentication failed",
            "status": 401,
            "detail": str(exc),
            "code": "AUTHENTICATION_FAILED",
            "trace_id": request.state.trace_id,
        },
    )


@app.exception_handler(AuthorizationError)
async def authorization_error_handler(request: Request, exc: AuthorizationError) -> JSONResponse:
    return JSONResponse(
        status_code=403,
        media_type="application/problem+json",
        content={
            "type": "about:blank",
            "title": "Forbidden",
            "status": 403,
            "detail": str(exc),
            "code": "FORBIDDEN",
            "trace_id": request.state.trace_id,
        },
    )


@app.exception_handler(RequestValidationError)
async def invalid_request(request: Request, exc: RequestValidationError) -> JSONResponse:
    return await http_problem_handler(
        request, HTTPException(422, "Invalid request parameters or body")
    )


@app.exception_handler(HTTPException)
async def http_problem_handler(request: Request, exc: HTTPException) -> JSONResponse:
    codes = {
        400: "BAD_REQUEST",
        401: "UNAUTHORIZED",
        403: "FORBIDDEN",
        404: "NOT_FOUND",
        409: "CONFLICT",
        422: "VALIDATION_FAILED",
        429: "RATE_LIMITED",
        503: "SERVICE_UNAVAILABLE",
    }
    return JSONResponse(
        status_code=exc.status_code,
        media_type="application/problem+json",
        headers=exc.headers,
        content={
            "type": "about:blank",
            "title": "Request failed",
            "status": exc.status_code,
            "detail": str(exc.detail),
            "code": codes.get(exc.status_code, "REQUEST_FAILED"),
            "trace_id": request.state.trace_id,
        },
    )


@app.get("/health/live", tags=["health"])
@app.get("/v1/health/live", tags=["health"])
async def live() -> dict[str, str]:
    """Report that the API process is responding."""
    return {"status": "live"}


@app.get("/health/ready", tags=["health"])
@app.get("/v1/health/ready", tags=["health"])
async def ready(request: Request) -> dict[str, str]:
    """Report process readiness and verify PostgreSQL when configured."""
    factory: async_sessionmaker[AsyncSession] | None = getattr(
        request.app.state, "session_factory", None
    )
    if factory is not None:
        try:
            async with factory() as session:
                await session.execute(text("SELECT 1"))
        except (SQLAlchemyError, OSError) as exc:
            raise HTTPException(status_code=503, detail="Database is not ready") from exc
    return {"status": "ready"}
