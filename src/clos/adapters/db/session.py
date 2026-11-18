"""Async database session and tenant RLS context management."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine


def make_session_factory(database_url: str) -> async_sessionmaker[AsyncSession]:
    engine = create_async_engine(database_url, pool_pre_ping=True)
    return async_sessionmaker(engine, expire_on_commit=False, autoflush=False)


@asynccontextmanager
async def tenant_session(
    factory: async_sessionmaker[AsyncSession], tenant_id: UUID
) -> AsyncIterator[AsyncSession]:
    """Start a transaction and set the tenant context consumed by PostgreSQL RLS."""
    async with factory() as session, session.begin():
        await session.execute(
            text("SELECT set_config('app.current_tenant_id', :tenant_id, true)"),
            {"tenant_id": str(tenant_id)},
        )
        yield session
