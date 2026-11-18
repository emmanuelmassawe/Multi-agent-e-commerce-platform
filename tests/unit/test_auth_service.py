"""Authentication use case tests using an in-memory fake repository."""

import asyncio
from dataclasses import dataclass
from datetime import UTC, datetime
from hashlib import sha256
from uuid import UUID, uuid4

import pytest

from clos.adapters.security.crypto import Argon2PasswordHasher, JwtTokenIssuer
from clos.application.auth import (
    AuthService,
    AuthenticationError,
    AuthorizationError,
    Principal,
)
from clos.domain.identity import Role


@dataclass
class FakeUser:
    id: UUID
    tenant_id: UUID
    email: str
    password_hash: str
    role: str
    is_active: bool = True


class FakeAuthRepository:
    def __init__(self, user: FakeUser, tenant_slug: str) -> None:
        self.user = user
        self.tenant_slug = tenant_slug
        self.refresh_tokens: dict[str, FakeUser] = {}
        self.api_keys: dict[str, tuple[FakeUser, str, list[str], datetime | None, datetime | None]] = {}
        self.idempotency: dict[str, tuple[str, UUID, str]] = {}
        self.revoked_keys: set[UUID] = set()

    async def get_tenant_id(self, tenant_slug: str) -> UUID | None:
        return self.user.tenant_id if tenant_slug == self.tenant_slug else None

    async def get_user_for_login(self, tenant_id: UUID, email: str) -> FakeUser | None:
        if tenant_id == self.user.tenant_id and email.casefold() == self.user.email.casefold():
            return self.user
        return None

    async def get_user(self, tenant_id: UUID, user_id: UUID) -> FakeUser | None:
        return self.user if (tenant_id, user_id) == (self.user.tenant_id, self.user.id) else None

    async def store_refresh_token(
        self, tenant_id: UUID, user_id: UUID, token_hash: str, expires_at: datetime
    ) -> None:
        if (tenant_id, user_id) == (self.user.tenant_id, self.user.id):
            self.refresh_tokens[token_hash] = self.user

    async def consume_refresh_token(self, tenant_id: UUID, token_hash: str) -> FakeUser | None:
        return self.refresh_tokens.pop(token_hash, None) if tenant_id == self.user.tenant_id else None

    async def create_api_key(
        self,
        tenant_id: UUID,
        user_id: UUID,
        label: str,
        prefix: str,
        key_hash: str,
        permissions: list[str],
        expires_at: datetime | None,
        idempotency_key: str,
        request_hash: str,
    ) -> UUID:
        prior = self.idempotency.get(idempotency_key)
        if prior is not None:
            if prior[0] != request_hash:
                raise ValueError("Idempotency-Key was already used with a different request")
            return prior[1]
        key_id = uuid4()
        self.idempotency[idempotency_key] = (request_hash, key_id, prefix)
        self.api_keys[prefix] = (self.user, key_hash, permissions, expires_at, None)
        return key_id

    async def revoke_api_key(self, tenant_id: UUID, key_id: UUID) -> bool:
        if tenant_id != self.user.tenant_id:
            return False
        self.revoked_keys.add(key_id)
        return True

    async def get_api_key(self, tenant_id: UUID, prefix: str):
        if tenant_id != self.user.tenant_id:
            return None
        return self.api_keys.get(prefix)

    async def update_api_key_last_used(self, tenant_id: UUID, prefix: str) -> None:
        del tenant_id, prefix


def make_service(role: Role = Role.OWNER) -> tuple[AuthService, FakeAuthRepository]:
    tenant_id = uuid4()
    user = FakeUser(
        id=uuid4(),
        tenant_id=tenant_id,
        email="owner@example.test",
        password_hash=Argon2PasswordHasher().hash("correct horse battery staple"),
        role=role.value,
    )
    repository = FakeAuthRepository(user, "shop-one")
    service = AuthService(
        repository,
        Argon2PasswordHasher(),
        JwtTokenIssuer("local-test-secret-that-is-at-least-32-characters"),
        access_token_seconds=60,
        refresh_token_days=1,
    )
    return service, repository


def test_login_and_refresh_rotate_refresh_token_once() -> None:
    async def scenario() -> None:
        service, _repo = make_service()
        pair = await service.login("shop-one", "OWNER@example.test", "correct horse battery staple")
        principal = await service.authenticate_access_token(pair.access_token)
        assert principal.role == Role.OWNER
        rotated = await service.refresh(pair.refresh_token)
        assert rotated.refresh_token != pair.refresh_token
        with pytest.raises(AuthenticationError):
            await service.refresh(pair.refresh_token)

    asyncio.run(scenario())


def test_invalid_password_and_tenant_do_not_authenticate() -> None:
    async def scenario() -> None:
        service, _repo = make_service()
        with pytest.raises(AuthenticationError):
            await service.login("shop-one", "owner@example.test", "incorrect password")
        with pytest.raises(AuthenticationError):
            await service.login("another-shop", "owner@example.test", "correct horse battery staple")

    asyncio.run(scenario())


def test_api_key_is_tenant_scoped_hashed_and_idempotent() -> None:
    async def scenario() -> None:
        service, repository = make_service()
        pair = await service.login("shop-one", "owner@example.test", "correct horse battery staple")
        principal = await service.authenticate_access_token(pair.access_token)
        key_id, api_key = await service.create_api_key(
            principal, "integration", ["read"], None, "request-1"
        )
        retry_id, retry_key = await service.create_api_key(
            principal, "integration", ["read"], None, "request-1"
        )
        assert retry_id == key_id
        assert retry_key == api_key
        stored = next(iter(repository.api_keys.values()))
        assert stored[1] == sha256(api_key.encode()).hexdigest()
        api_principal = await service.authenticate_api_key(api_key)
        assert api_principal.tenant_id == principal.tenant_id
        assert api_principal.allows("read")
        assert not api_principal.allows("manage_api_keys")
        with pytest.raises(ValueError, match="different request"):
            await service.create_api_key(
                principal, "renamed", ["read"], None, "request-1"
            )

    asyncio.run(scenario())


def test_viewer_cannot_create_integration_api_keys() -> None:
    async def scenario() -> None:
        service, _repo = make_service(Role.VIEWER)
        viewer = Principal(uuid4(), uuid4(), Role.VIEWER, "viewer@example.test")
        with pytest.raises(AuthorizationError):
            await service.create_api_key(viewer, "blocked", ["read"], None, "request-2")

    asyncio.run(scenario())

