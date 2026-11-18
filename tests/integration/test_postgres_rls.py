"""Real PostgreSQL RLS tests, enabled with TEST_DATABASE_URL after migrations."""

import asyncio
import os

import pytest
from sqlalchemy import delete, select, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from clos.adapters.db.models import Product, Tenant
from clos.domain.ids import new_uuid7

TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(
    TEST_DATABASE_URL is None, reason="TEST_DATABASE_URL is not configured"
)


def test_postgres_rls_blocks_other_tenants_for_raw_queries() -> None:
    assert TEST_DATABASE_URL is not None

    async def scenario() -> None:
        engine = create_async_engine(TEST_DATABASE_URL)
        factory = async_sessionmaker(engine, expire_on_commit=False)
        tenant_a = Tenant(
            id=new_uuid7(), slug=f"test-a-{new_uuid7().hex[:10]}", name="Test A"
        )
        tenant_b = Tenant(
            id=new_uuid7(), slug=f"test-b-{new_uuid7().hex[:10]}", name="Test B"
        )
        product_a = Product(
            tenant_id=tenant_a.id,
            sku="A-1",
            name="Tenant A product",
            currency="TZS",
        )
        product_b = Product(
            tenant_id=tenant_b.id,
            sku="B-1",
            name="Tenant B product",
            currency="TZS",
        )
        async with factory() as session, session.begin():
            session.add_all([tenant_a, tenant_b])
        async with factory() as session, session.begin():
            await session.execute(
                text("SELECT set_config('app.current_tenant_id', :tenant_id, true)"),
                {"tenant_id": str(tenant_a.id)},
            )
            session.add(product_a)
        async with factory() as session, session.begin():
            await session.execute(
                text("SELECT set_config('app.current_tenant_id', :tenant_id, true)"),
                {"tenant_id": str(tenant_b.id)},
            )
            session.add(product_b)
        async with factory() as session, session.begin():
            await session.execute(
                text("SELECT set_config('app.current_tenant_id', :tenant_id, true)"),
                {"tenant_id": str(tenant_a.id)},
            )
            result = await session.execute(select(Product).where(Product.id == product_b.id))
            assert result.scalar_one_or_none() is None
        async with factory() as session, session.begin():
            await session.execute(
                text("SELECT set_config('app.current_tenant_id', :tenant_id, true)"),
                {"tenant_id": str(tenant_a.id)},
            )
            invisible = await session.execute(select(Product).where(Product.id == product_b.id))
            assert invisible.scalar_one_or_none() is None
            with pytest.raises(DBAPIError):
                async with session.begin_nested():
                    session.add(
                        Product(
                            tenant_id=tenant_b.id,
                            sku="A-2",
                            name="Cross tenant write",
                            currency="TZS",
                        )
                    )
                    await session.flush()
        async with factory() as session, session.begin():
            await session.execute(delete(Tenant).where(Tenant.id.in_([tenant_a.id, tenant_b.id])))
        await engine.dispose()

    asyncio.run(scenario())

