"""Atomic, bounded Redis counters for authenticated tenant and actor quotas."""
from dataclasses import dataclass
from typing import Protocol, cast
from uuid import UUID

from redis.asyncio import Redis

_SCRIPT = """
local ttl = 60
local remaining = {}
local reset = {}
for i = 1, 2 do
  remaining[i] = tonumber(ARGV[i]) - tonumber(redis.call('GET', KEYS[i]) or '0')
  reset[i] = redis.call('TTL', KEYS[i])
  if reset[i] < 1 then reset[i] = ttl end
end
for i = 1, 2 do
  if remaining[i] <= 0 then return {0, tonumber(ARGV[i]), 0, reset[i]} end
end
for i = 1, 2 do
  if redis.call('INCR', KEYS[i]) == 1 then redis.call('EXPIRE', KEYS[i], ttl) end
end
local i = remaining[1] <= remaining[2] and 1 or 2
return {1, tonumber(ARGV[i]), remaining[i]-1, reset[i]}
"""


@dataclass(frozen=True)
class Quota:
    allowed: bool
    limit: int
    remaining: int
    reset: int

    def headers(self) -> dict[str,str]:
        return {"RateLimit-Limit":str(self.limit),"RateLimit-Remaining":str(self.remaining),
                "RateLimit-Reset":str(self.reset)}


class RateLimitPort(Protocol):
    async def take(self,tenant: UUID,actor: str) -> Quota: ...


class RedisRateLimit:
    def __init__(self,redis: Redis,tenant_limit: int,user_limit: int) -> None:
        self.redis=redis
        self.tenant_limit=tenant_limit
        self.user_limit=user_limit

    async def take(self,tenant: UUID,actor: str) -> Quota:
        prefix=f"clos:quota:{{{tenant}}}"
        raw=await self.redis.eval(_SCRIPT,2,prefix,prefix+":"+actor,self.tenant_limit,self.user_limit)
        allowed,limit,remaining,reset=cast(list[int],raw)
        return Quota(bool(allowed),limit,remaining,reset)
