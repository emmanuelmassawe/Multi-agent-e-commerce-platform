"""Expiring tenant/customer-scoped Redis session summaries."""

from uuid import UUID

from redis.asyncio import Redis


class RedisSessionCache:
    def __init__(self, client: Redis) -> None:
        self.client = client

    @staticmethod
    def key(tenant: UUID, customer: UUID) -> str:
        return f"clos:session:{tenant}:{customer}"

    async def read(self, tenant: UUID, customer: UUID) -> str | None:
        result = await self.client.get(self.key(tenant, customer))
        return result.decode() if isinstance(result, bytes) else result

    async def write(self, tenant: UUID, customer: UUID, value: str) -> None:
        await self.client.set(self.key(tenant, customer), value, ex=900)

    async def erase(self, tenant: UUID, customer: UUID) -> None:
        await self.client.delete(self.key(tenant, customer))
