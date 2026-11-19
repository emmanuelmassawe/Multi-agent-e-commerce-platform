"""Process-local resources for one request or worker invocation."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import httpx
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from clos.adapters.db.memory import MemoryRepository
from clos.adapters.qdrant import QdrantVectorStore
from clos.adapters.session_cache import RedisSessionCache
from clos.config import settings


@asynccontextmanager
async def memory_runtime(
    sessions: async_sessionmaker[AsyncSession],
) -> AsyncIterator[MemoryRepository]:
    async with (
        httpx.AsyncClient(base_url=settings.qdrant_url, timeout=30) as client,
        Redis.from_url(settings.redis_url, socket_timeout=5) as redis,
    ):
        yield MemoryRepository(
            sessions,
            QdrantVectorStore(client, settings.qdrant_collection),
            RedisSessionCache(redis),
        )
