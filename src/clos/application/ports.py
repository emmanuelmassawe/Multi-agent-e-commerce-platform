"""Ports required by application use cases."""

from collections.abc import Sequence
from datetime import datetime
from typing import Protocol
from uuid import UUID

from clos.domain.identity import Role


class AuthUser(Protocol):
    id: UUID
    tenant_id: UUID
    email: str
    password_hash: str
    role: str
    is_active: bool


class AuthRepositoryPort(Protocol):
    async def get_tenant_id(self, tenant_slug: str) -> UUID | None: ...

    async def get_user_for_login(self, tenant_id: UUID, email: str) -> AuthUser | None: ...

    async def get_user(self, tenant_id: UUID, user_id: UUID) -> AuthUser | None: ...

    async def store_refresh_token(
        self,
        tenant_id: UUID,
        user_id: UUID,
        token_hash: str,
        expires_at: datetime,
    ) -> None: ...

    async def consume_refresh_token(self, tenant_id: UUID, token_hash: str) -> AuthUser | None: ...

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
    ) -> UUID: ...

    async def revoke_api_key(self, tenant_id: UUID, key_id: UUID) -> bool: ...

    async def get_api_key(
        self, tenant_id: UUID, prefix: str
    ) -> tuple[AuthUser, str, Sequence[str], datetime | None, datetime | None] | None: ...

    async def update_api_key_last_used(self, tenant_id: UUID, prefix: str) -> None: ...


class PasswordHasherPort(Protocol):
    def hash(self, password: str) -> str: ...

    def verify(self, password: str, password_hash: str) -> bool: ...


class TokenIssuerPort(Protocol):
    def create_access_token(
        self, *, user_id: UUID, tenant_id: UUID, role: Role, expires_in_seconds: int
    ) -> str: ...

    def decode_access_token(self, token: str) -> tuple[UUID, UUID, Role]: ...

    def create_refresh_token(
        self, *, user_id: UUID, tenant_id: UUID, expires_in_seconds: int
    ) -> tuple[str, str, datetime]: ...

    def hash_refresh_token(self, token: str) -> str: ...

    def decode_refresh_token(self, token: str) -> tuple[UUID, UUID]: ...

    def derive_api_key(self, tenant_id: UUID, idempotency_key: str) -> tuple[str, str]: ...
