"""Qdrant REST adapter. Every read and deletion carries a tenant filter."""

from typing import Any
from uuid import UUID

import httpx

from clos.application.memory import DIMENSIONS, Point, features


def match(key: str, value: str) -> dict[str, Any]:
    return {"key": key, "match": {"value": value}}


def scope(tenant: UUID) -> dict[str, Any]:
    return {"must": [match("tenant_id", str(tenant))]}


class QdrantVectorStore:
    def __init__(self, client: httpx.AsyncClient, collection: str) -> None:
        self.client = client
        self.path = f"/collections/{collection}"
        self.initialized = False

    async def ensure(self) -> None:
        if self.initialized:
            return
        response = await self.client.get(self.path)
        if response.status_code == 404:
            created = await self.client.put(
                self.path,
                json={
                    "vectors": {"dense": {"size": DIMENSIONS, "distance": "Cosine"}},
                    "sparse_vectors": {"bm25": {"modifier": "idf"}},
                },
            )
            if created.status_code != 409:
                created.raise_for_status()
        else:
            response.raise_for_status()
        for key in ("tenant_id", "customer_id"):
            result = await self.client.put(
                self.path + "/index?wait=true",
                json={
                    "field_name": key,
                    "field_schema": "keyword",
                },
            )
            result.raise_for_status()
        self.initialized = True

    async def upsert(self, points: list[Point]) -> None:
        await self.ensure()
        for i in range(0, len(points), 64):
            batch = []
            for p in points[i : i + 64]:
                vec = features(p.text)
                batch.append(
                    {
                        "id": str(p.id),
                        "payload": {
                            "tenant_id": str(p.tenant_id),
                            "customer_id": str(p.customer_id or "shared"),
                            "checksum": p.checksum,
                        },
                        "vector": {
                            "dense": vec.dense,
                            "bm25": {
                                "indices": list(vec.sparse),
                                "values": list(vec.sparse.values()),
                            },
                        },
                    }
                )
            (
                await self.client.put(self.path + "/points?wait=true", json={"points": batch})
            ).raise_for_status()

    async def _delete(self, where: dict[str, Any]) -> None:
        await self.ensure()
        (
            await self.client.post(self.path + "/points/delete?wait=true", json={"filter": where})
        ).raise_for_status()

    async def remove(self, tenant: UUID, ids: list[UUID]) -> None:
        for i in range(0, len(ids), 100):
            where = scope(tenant)
            where["must"].append({"has_id": [str(uid) for uid in ids[i : i + 100]]})
            await self._delete(where)

    async def erase(self, tenant: UUID, customer: UUID) -> None:
        where = scope(tenant)
        where["must"].append(match("customer_id", str(customer)))
        await self._delete(where)

    async def manifest(self, tenant: UUID) -> dict[UUID, str]:
        await self.ensure()
        result: dict[UUID, str] = {}
        offset = None
        while True:
            response = await self.client.post(
                self.path + "/points/scroll",
                json={
                    "filter": scope(tenant),
                    "offset": offset,
                    "limit": 256,
                    "with_payload": ["checksum"],
                    "with_vector": False,
                },
            )
            page = response.raise_for_status().json()["result"]
            result.update({UUID(p["id"]): p["payload"].get("checksum", "") for p in page["points"]})
            offset = page.get("next_page_offset")
            if offset is None:
                return result

    async def query(
        self, tenant: UUID, customer: UUID, query: str, limit: int, *, hybrid: bool = True
    ) -> list[UUID]:
        await self.ensure()
        vec = features(query)
        if not vec.sparse:
            return []
        where = scope(tenant)
        where["must"].append({"key": "customer_id", "match": {"any": [str(customer), "shared"]}})
        body: dict[str, Any] = {"filter": where, "limit": limit}
        if hybrid:
            body.update(
                prefetch=[
                    {"using": "dense", "query": vec.dense, "filter": where, "limit": limit * 3},
                    {
                        "using": "bm25",
                        "query": {"indices": list(vec.sparse), "values": list(vec.sparse.values())},
                        "filter": where,
                        # Only lexical matches should contribute a sparse rank to RRF.
                        "score_threshold": 1e-12,
                        "limit": limit * 3,
                    },
                ],
                query={"fusion": "rrf"},
            )
        else:
            body.update(query=vec.dense, using="dense")
        response = await self.client.post(self.path + "/points/query", json=body)
        points = response.raise_for_status().json()["result"]["points"]
        points.sort(key=lambda point: (-point["score"], point["id"]))
        return [UUID(point["id"]) for point in points]
