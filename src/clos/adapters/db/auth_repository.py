"""SQLAlchemy implementation of the authentication repository port."""

from collections.abc import Sequence
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from clos.adapters.db.models import ApiKey, AuditLog, RefreshToken, Tenant, User
from clos.application.ports import AuthUser


class SqlAlchemyAuthRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_tenant_id(self, tenant_slug: str) -> UUID | None:
        result = await self._session.execute(
            select(Tenant.id).where(Tenant.slug == tenant_slug, Tenant.is_active.is_(True))
        )
        return result.scalar_one_or_none()

    async def get_user_for_login(self, tenant_id: UUID, email: str) -> User | None:
        await self._set_tenant(tenant_id)
        result = await self._session.execute(
            select(User).where(
                User.tenant_id == tenant_id,
                User.email == email.strip().casefold(),
            )
        )
        return result.scalar_one_or_none()

    async def get_user(self, tenant_id: UUID, user_id: UUID) -> User | None:
        await self._set_tenant(tenant_id)
        result = await self._session.execute(
            select(User).where(User.tenant_id == tenant_id, User.id == user_id)
        )
        return result.scalar_one_or_none()

    async def store_refresh_token(
        self, tenant_id: UUID, user_id: UUID, token_hash: str, expires_at: datetime
    ) -> None:
        await self._set_tenant(tenant_id)
        self._session.add(
            RefreshToken(
                tenant_id=tenant_id,
                user_id=user_id,
                token_hash=token_hash,
                expires_at=expires_at,
            )
        )
        await self._session.flush()

    async def consume_refresh_token(self, tenant_id: UUID, token_hash: str) -> User | None:
        await self._set_tenant(tenant_id)
        result = await self._session.execute(
            select(RefreshToken)
            .where(
                RefreshToken.tenant_id == tenant_id,
                RefreshToken.token_hash == token_hash,
                RefreshToken.revoked_at.is_(None),
                RefreshToken.expires_at > datetime.now(UTC),
            )
            .with_for_update()
        )
        token_record = result.scalar_one_or_none()
        if token_record is None:
            return None
        token_record.revoked_at = datetime.now(UTC)
        return await self.get_user(tenant_id, token_record.user_id)

    async def create_api_key(
        self,
        tenant_id: UUID,
        user_id: UUID,
        label: str,
        prefix: str,
        key_hash: str,
        permissions: Sequence[str],
        expires_at: datetime | None,
        idempotency_key: str,
        request_hash: str,
    ) -> UUID:
        await self._set_tenant(tenant_id)
        existing_result = await self._session.execute(
            select(ApiKey).where(
                ApiKey.tenant_id == tenant_id,
                ApiKey.idempotency_key == idempotency_key,
            )
        )
        existing = existing_result.scalar_one_or_none()
        if existing is not None:
            if existing.request_hash != request_hash:
                raise ValueError("Idempotency-Key was already used with a different request")
            return existing.id
        key = ApiKey(
            tenant_id=tenant_id,
            user_id=user_id,
            label=label,
            prefix=prefix,
            key_hash=key_hash,
            permissions=list(permissions),
            idempotency_key=idempotency_key,
            request_hash=request_hash,
            expires_at=expires_at,
        )
        self._session.add(key)
        self._session.add(
            AuditLog(
                tenant_id=tenant_id,
                actor_id=user_id,
                action="api_key.created",
                entity_type="api_key",
                details={"label": label, "permissions": list(permissions)},
            )
        )
        await self._session.flush()
        return key.id

    async def revoke_api_key(self, tenant_id: UUID, key_id: UUID) -> bool:
        await self._set_tenant(tenant_id)
        result = await self._session.execute(
            select(ApiKey).where(ApiKey.tenant_id == tenant_id, ApiKey.id == key_id)
        )
        key = result.scalar_one_or_none()
        if key is None:
            return False
        if key.revoked_at is not None:
            return True
        key.revoked_at = datetime.now(UTC)
        self._session.add(
            AuditLog(
                tenant_id=tenant_id,
                actor_id=key.user_id,
                action="api_key.revoked",
                entity_type="api_key",
                entity_id=key.id,
                details={"label": key.label},
            )
        )
        await self._session.flush()
        return True

    async def get_api_key(
        self, tenant_id: UUID, prefix: str
    ) -> tuple[AuthUser, str, Sequence[str], datetime | None, datetime | None] | None:
        await self._set_tenant(tenant_id)
        result = await self._session.execute(
            select(ApiKey, User)
            .join(User, (User.id == ApiKey.user_id) & (User.tenant_id == ApiKey.tenant_id))
            .where(ApiKey.tenant_id == tenant_id, ApiKey.prefix == prefix)
        )
        row = result.first()
        if row is None:
            return None
        key, user = row
        return user, key.key_hash, key.permissions, key.expires_at, key.revoked_at

    async def update_api_key_last_used(self, tenant_id: UUID, prefix: str) -> None:
        await self._set_tenant(tenant_id)
        result = await self._session.execute(
            select(ApiKey).where(ApiKey.tenant_id == tenant_id, ApiKey.prefix == prefix)
        )
        key = result.scalar_one_or_none()
        if key is not None:
            key.last_used_at = datetime.now(UTC)
            await self._session.flush()

    async def _set_tenant(self, tenant_id: UUID) -> None:
        from sqlalchemy import text

        await self._session.execute(
            text("SELECT set_config('app.current_tenant_id', :tenant_id, true)"),
            {"tenant_id": str(tenant_id)},
        )
