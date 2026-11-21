"""Shared runtime controls for API admission and scheduled integration work."""

from uuid import UUID

from redis.asyncio import Redis

from clos.config import settings


class DeliveryPaused(RuntimeError):
    pass


async def check_active(tenant: UUID) -> None:
    async with Redis.from_url(
        settings.redis_url, socket_connect_timeout=2, socket_timeout=2
    ) as redis:
        global_stop, tenant_stop = await redis.mget(["clos:pause:global", f"clos:pause:{tenant}"])
        if global_stop or tenant_stop:
            raise DeliveryPaused("Delivery paused by operator")


async def circuit_open(tenant: UUID, kind: str) -> bool:
    async with Redis.from_url(settings.redis_url, socket_timeout=2) as redis:
        return bool(await redis.exists(f"clos:circuit:{tenant}:{kind}"))


async def cool_down(tenant: UUID, kind: str) -> None:
    async with Redis.from_url(settings.redis_url, socket_timeout=2) as redis:
        await redis.set(f"clos:circuit:{tenant}:{kind}", "open", ex=30)
