"""Local retrieval features and the tenant-scoped projection boundary."""

import hashlib
import math
import re
from collections import Counter
from dataclasses import dataclass
from typing import Protocol
from uuid import UUID

DIMENSIONS = 256


def passages(text: str) -> list[str]:
    """Chunk normalized plain text, including long unbroken tokens."""
    clean = " ".join(text.split())
    if not clean:
        raise ValueError("Document cannot be blank")
    return [clean[i : i + 1000] for i in range(0, len(clean), 1000)]


@dataclass(frozen=True)
class Features:
    dense: list[float]
    sparse: dict[int, float]


def features(text: str) -> Features:
    tokens = re.findall(r"\w+", text.casefold())
    dense = [0.0] * DIMENSIONS
    sparse: dict[int, float] = {}
    for term, count in Counter(tokens).items():
        digest = hashlib.blake2s(term.encode(), digest_size=8).digest()
        index = int.from_bytes(digest[:4], "big")
        weight = count * 2.2 / (count + 1.2 * (0.25 + 0.75 * len(tokens) / 100))
        sparse[index] = sparse.get(index, 0) + weight
        dense[index % DIMENSIONS] += (1 if digest[4] & 1 else -1) * math.log1p(count)
    norm = math.sqrt(sum(v * v for v in dense)) or 1
    return Features([v / norm for v in dense], sparse)


@dataclass(frozen=True)
class Point:
    id: UUID
    tenant_id: UUID
    customer_id: UUID | None
    text: str

    @property
    def checksum(self) -> str:
        data = f"hash-bm25-v1:{self.tenant_id}:{self.customer_id}:{self.text}"
        return hashlib.sha256(data.encode()).hexdigest()


class VectorStorePort(Protocol):
    async def upsert(self, points: list[Point]) -> None: ...
    async def remove(self, tenant: UUID, ids: list[UUID]) -> None: ...
    async def manifest(self, tenant: UUID) -> dict[UUID, str]: ...
    async def erase(self, tenant: UUID, customer: UUID) -> None: ...
    async def query(
        self, tenant: UUID, customer: UUID, query: str, limit: int, *, hybrid: bool = True
    ) -> list[UUID]: ...


class SessionCachePort(Protocol):
    async def read(self, tenant: UUID, customer: UUID) -> str | None: ...
    async def write(self, tenant: UUID, customer: UUID, value: str) -> None: ...
    async def erase(self, tenant: UUID, customer: UUID) -> None: ...
