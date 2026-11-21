from uuid import UUID

from fastapi import HTTPException, Request
from redis.exceptions import RedisError

from clos.adapters.quota import RateLimitPort


async def enforce(request: Request,tenant: UUID,actor: str) -> None:
    limiter: RateLimitPort | None = getattr(request.app.state,"limiter",None)
    if limiter is None:
        raise HTTPException(503,"Rate limiter unavailable")
    try:
        quota=await limiter.take(tenant,actor)
    except RedisError as exc:
        raise HTTPException(503,"Rate limiter unavailable") from exc
    request.state.rate_headers=quota.headers()
    if not quota.allowed:
        raise HTTPException(429,"Request quota exhausted",headers={"Retry-After":str(quota.reset)})
