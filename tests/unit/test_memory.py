import asyncio
from uuid import uuid4

import pytest

from clos.adapters.memory_fakes import InMemoryVectorStore
from clos.application.memory import Point, features, passages


def test_local_embedding_and_chunking() -> None:
    with pytest.raises(ValueError):
        passages("   ")
    assert "".join(passages("a" * 1200)) == "a" * 1200
    assert features("Price price") == features("price PRICE")
    assert features("!!!").sparse == {}


def test_fake_projection_boundary() -> None:
    async def scenario() -> None:
        store = InMemoryVectorStore()
        tenant, customer = uuid4(), uuid4()
        point = Point(uuid4(), tenant, customer, "order")
        await store.upsert([point, point, Point(uuid4(), uuid4(), customer, "order")])
        assert await store.query(tenant, customer, "order", 3) == [point.id]
        assert not await store.query(tenant, uuid4(), "order", 3)
        await store.erase(tenant, customer)
        assert await store.manifest(tenant) == {}

    asyncio.run(scenario())
