"""Tenant-scoped repository behavior using an async SQLite test database."""

import asyncio

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from clos.adapters.db.models import Base, Product, Tenant
from clos.adapters.db.repositories import TenantRepository
from clos.domain.ids import new_uuid7


def test_repository_filters_reads_and_rejects_cross_tenant_writes() -> None:
    async def scenario() -> None:
        engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        factory = async_sessionmaker(engine, expire_on_commit=False)
        tenant_a = Tenant(id=new_uuid7(), slug="alpha", name="Alpha")
        tenant_b = Tenant(id=new_uuid7(), slug="beta", name="Beta")
        product_a = Product(
            tenant_id=tenant_a.id,
            sku="A-1",
            name="A product",
            currency="TZS",
        )
        product_b = Product(
            tenant_id=tenant_b.id,
            sku="B-1",
            name="B product",
            currency="TZS",
        )
        async with factory() as session:
            session.add_all([tenant_a, tenant_b, product_a, product_b])
            await session.commit()
            repository = TenantRepository(session, Product, tenant_a.id)
            assert await repository.get(product_b.id) is None
            assert [row.id for row in await repository.list()] == [product_a.id]
            try:
                await repository.add(product_b)
            except ValueError as error:
                assert "tenant_id" in str(error)
            else:
                raise AssertionError("Cross-tenant entity was accepted")
        await engine.dispose()

    asyncio.run(scenario())

