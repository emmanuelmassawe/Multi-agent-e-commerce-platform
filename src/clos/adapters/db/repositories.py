"""Tenant-scoped SQLAlchemy repositories."""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from clos.adapters.db.models import TenantScoped


class TenantRepository[ModelT: TenantScoped]:
    """Repository that adds an explicit tenant filter to every read."""

    def __init__(self, session: AsyncSession, model: type[ModelT], tenant_id: UUID) -> None:
        self._session = session
        self._model = model
        self._tenant_id = tenant_id

    async def get(self, entity_id: UUID) -> ModelT | None:
        result = await self._session.execute(
            select(self._model).where(
                self._model.id == entity_id,
                self._model.tenant_id == self._tenant_id,
            )
        )
        return result.scalar_one_or_none()

    async def list(self, *, limit: int = 100) -> list[ModelT]:
        result = await self._session.execute(
            select(self._model)
            .where(self._model.tenant_id == self._tenant_id)
            .order_by(self._model.created_at, self._model.id)
            .limit(min(max(limit, 1), 500))
        )
        return list(result.scalars().all())

    async def add(self, entity: ModelT) -> ModelT:
        if entity.tenant_id != self._tenant_id:
            raise ValueError("Entity tenant_id does not match repository scope")
        self._session.add(entity)
        await self._session.flush()
        return entity
