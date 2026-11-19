"""In-memory memory ports for offline tests."""

from uuid import UUID

from clos.application.memory import Point, features


class InMemoryVectorStore:
    def __init__(self) -> None:
        self.points: dict[UUID, Point] = {}

    async def upsert(self, points: list[Point]) -> None:
        self.points.update({p.id: p for p in points})

    async def remove(self, tenant: UUID, ids: list[UUID]) -> None:
        for uid in ids:
            if uid in self.points and self.points[uid].tenant_id == tenant:
                del self.points[uid]

    async def erase(self, tenant: UUID, customer: UUID) -> None:
        await self.remove(tenant, [p.id for p in self.points.values() if p.customer_id == customer])

    async def manifest(self, tenant: UUID) -> dict[UUID, str]:
        return {p.id: p.checksum for p in self.points.values() if p.tenant_id == tenant}

    async def query(
        self, tenant: UUID, customer: UUID, query: str, limit: int, *, hybrid: bool = True
    ) -> list[UUID]:
        terms = features(query)
        scores = {}
        for point in self.points.values():
            if point.tenant_id == tenant and point.customer_id in (customer, None):
                vec = features(point.text)
                score = sum(a * b for a, b in zip(terms.dense, vec.dense, strict=True))
                if hybrid:
                    score += sum(
                        terms.sparse[k] * vec.sparse[k]
                        for k in terms.sparse.keys() & vec.sparse.keys()
                    )
                scores[point.id] = score
        return sorted(scores, key=scores.__getitem__, reverse=True)[:limit]


class InMemorySessionCache:
    def __init__(self) -> None:
        self.sessions: dict[tuple[UUID, UUID], str] = {}

    async def read(self, tenant: UUID, customer: UUID) -> str | None:
        return self.sessions.get((tenant, customer))

    async def write(self, tenant: UUID, customer: UUID, value: str) -> None:
        self.sessions[tenant, customer] = value

    async def erase(self, tenant: UUID, customer: UUID) -> None:
        self.sessions.pop((tenant, customer), None)
