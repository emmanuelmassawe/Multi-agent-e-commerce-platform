"""Create a tenant and owner from environment-provided seed values."""

from __future__ import annotations

import asyncio
import os

from sqlalchemy import select, text

from clos.adapters.db.auth_repository import SqlAlchemyAuthRepository
from clos.adapters.db.models import AutonomySetting, Tenant, User
from clos.adapters.db.session import make_session_factory
from clos.adapters.security.crypto import Argon2PasswordHasher
from clos.config import settings
from clos.domain.identity import Role


async def seed() -> None:
    database_url = settings.database_admin_url or settings.database_url
    if database_url is None:
        raise RuntimeError("DATABASE_ADMIN_URL or DATABASE_URL must be set")
    tenant_slug = os.environ.get("SEED_TENANT_SLUG", "").strip()
    owner_email = os.environ.get("SEED_OWNER_EMAIL", "").strip().casefold()
    owner_password = os.environ.get("SEED_OWNER_PASSWORD", "")
    if not tenant_slug or not owner_email or len(owner_password) < 12:
        raise RuntimeError(
            "Set SEED_TENANT_SLUG, SEED_OWNER_EMAIL, and a SEED_OWNER_PASSWORD "
            "of at least 12 characters"
        )

    factory = make_session_factory(database_url)
    async with factory() as session, session.begin():
        tenant_result = await session.execute(select(Tenant).where(Tenant.slug == tenant_slug))
        tenant = tenant_result.scalar_one_or_none()
        if tenant is None:
            tenant = Tenant(slug=tenant_slug, name=tenant_slug.replace("-", " ").title())
            session.add(tenant)
            await session.flush()
        await session.execute(
            text("SELECT set_config('app.current_tenant_id', :tenant_id, true)"),
            {"tenant_id": str(tenant.id)},
        )
        repository = SqlAlchemyAuthRepository(session)
        owner = await repository.get_user_for_login(tenant.id, owner_email)
        if owner is None:
            session.add(
                User(
                    tenant_id=tenant.id,
                    email=owner_email,
                    full_name=os.environ.get("SEED_OWNER_NAME", "Tenant Owner"),
                    password_hash=Argon2PasswordHasher().hash(owner_password),
                    role=Role.OWNER.value,
                    is_active=True,
                )
            )
            print(f"Seeded tenant owner for tenant {tenant_slug!r}")
        else:
            print(f"Tenant owner already exists for tenant {tenant_slug!r}")
        configured_agents = await session.execute(
            select(AutonomySetting.agent_name).where(AutonomySetting.tenant_id == tenant.id)
        )
        existing_agents = set(configured_agents.scalars().all())
        for agent_name in ("inventory", "pricing", "logistics", "support"):
            if agent_name not in existing_agents:
                session.add(
                    AutonomySetting(
                        tenant_id=tenant.id,
                        agent_name=agent_name,
                        mode="shadow",
                    )
                )
    await factory.kw["bind"].dispose()


if __name__ == "__main__":
    asyncio.run(seed())
