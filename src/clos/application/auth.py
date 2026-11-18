"""Application use cases for login, refresh tokens, API keys, and authorization."""

from dataclasses import dataclass
from datetime import UTC, datetime
from hashlib import sha256
from hmac import compare_digest
import json
from uuid import UUID

from clos.application.ports import (
    AuthRepositoryPort,
    AuthUser,
    PasswordHasherPort,
    TokenIssuerPort,
)
from clos.domain.identity import Role, role_allows


class AuthenticationError(Exception):
    """Raised when credentials or a token are invalid."""


class AuthorizationError(Exception):
    """Raised when an authenticated principal lacks permission."""


@dataclass(frozen=True, slots=True)
class TokenPair:
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


@dataclass(frozen=True, slots=True)
class Principal:
    user_id: UUID
    tenant_id: UUID
    role: Role
    email: str
    api_key_permissions: frozenset[str] | None = None

    def allows(self, permission: str) -> bool:
        if self.api_key_permissions is not None:
            return "*" in self.api_key_permissions or permission in self.api_key_permissions
        return role_allows(self.role, permission)


class AuthService:
    def __init__(
        self,
        repository: AuthRepositoryPort,
        password_hasher: PasswordHasherPort,
        token_issuer: TokenIssuerPort,
        *,
        access_token_seconds: int = 900,
        refresh_token_days: int = 30,
    ) -> None:
        self._repository = repository
        self._password_hasher = password_hasher
        self._token_issuer = token_issuer
        self._access_token_seconds = access_token_seconds
        self._refresh_token_days = refresh_token_days

    async def login(self, tenant_slug: str, email: str, password: str) -> TokenPair:
        tenant_id = await self._repository.get_tenant_id(tenant_slug)
        user = (
            await self._repository.get_user_for_login(tenant_id, email)
            if tenant_id is not None
            else None
        )
        if (
            user is None
            or not user.is_active
            or not self._password_hasher.verify(password, user.password_hash)
        ):
            raise AuthenticationError("Invalid credentials")
        return await self._issue_pair(user)

    async def refresh(self, refresh_token: str) -> TokenPair:
        try:
            user_id, tenant_id = self._token_issuer.decode_refresh_token(refresh_token)
        except Exception as exc:
            raise AuthenticationError("Invalid refresh token") from exc
        user = await self._repository.consume_refresh_token(
            tenant_id, self._token_issuer.hash_refresh_token(refresh_token)
        )
        if user is None or user.id != user_id or not user.is_active:
            raise AuthenticationError("Invalid refresh token")
        return await self._issue_pair(user)

    async def authenticate_access_token(self, token: str) -> Principal:
        try:
            user_id, tenant_id, _claimed_role = self._token_issuer.decode_access_token(token)
        except Exception as exc:
            raise AuthenticationError("Invalid access token") from exc
        user = await self._repository.get_user(tenant_id, user_id)
        if user is None or not user.is_active:
            raise AuthenticationError("Invalid access token")
        return self._principal(user)

    async def authenticate_api_key(self, api_key: str) -> Principal:
        parts = api_key.split(".")
        if len(parts) != 4 or parts[0] != "clos":
            raise AuthenticationError("Invalid API key")
        try:
            tenant_id = UUID(parts[1])
        except ValueError as exc:
            raise AuthenticationError("Invalid API key") from exc
        prefix, _separator, _secret = parts[2].partition("_")
        record = await self._repository.get_api_key(tenant_id, prefix)
        if record is None:
            raise AuthenticationError("Invalid API key")
        user, key_hash, permissions, expires_at, revoked_at = record
        if (
            revoked_at is not None
            or (expires_at is not None and expires_at <= datetime.now(UTC))
            or not compare_digest(sha256(api_key.encode()).hexdigest(), key_hash)
            or not user.is_active
        ):
            raise AuthenticationError("Invalid API key")
        await self._repository.update_api_key_last_used(tenant_id, prefix)
        return Principal(
            user_id=user.id,
            tenant_id=tenant_id,
            role=Role(user.role),
            email=user.email,
            api_key_permissions=frozenset(permissions),
        )

    async def create_api_key(
        self,
        principal: Principal,
        label: str,
        permissions: list[str],
        expires_at: datetime | None,
        idempotency_key: str,
    ) -> tuple[UUID, str]:
        if not principal.allows("manage_api_keys"):
            raise AuthorizationError("Permission denied")
        if not permissions or any(not principal.allows(permission) for permission in permissions):
            raise AuthorizationError("Requested API key permissions exceed caller permissions")
        if not idempotency_key or len(idempotency_key) > 200:
            raise ValueError("Idempotency-Key must contain between 1 and 200 characters")
        prefix, raw_key = self._token_issuer.derive_api_key(
            principal.tenant_id, idempotency_key
        )
        key_hash = sha256(raw_key.encode()).hexdigest()
        request_hash = sha256(
            json.dumps(
                {"label": label, "permissions": sorted(permissions), "expires_at": expires_at},
                sort_keys=True,
                default=str,
                separators=(",", ":"),
            ).encode()
        ).hexdigest()
        key_id = await self._repository.create_api_key(
            principal.tenant_id,
            principal.user_id,
            label,
            prefix,
            key_hash,
            permissions,
            expires_at,
            idempotency_key,
            request_hash,
        )
        return key_id, raw_key

    async def revoke_api_key(self, principal: Principal, key_id: UUID) -> bool:
        if not principal.allows("manage_api_keys"):
            raise AuthorizationError("Permission denied")
        return await self._repository.revoke_api_key(principal.tenant_id, key_id)

    async def _issue_pair(self, user: AuthUser) -> TokenPair:
        user_id = user.id
        tenant_id = user.tenant_id
        role = Role(user.role)
        access = self._token_issuer.create_access_token(
            user_id=user_id,
            tenant_id=tenant_id,
            role=role,
            expires_in_seconds=self._access_token_seconds,
        )
        refresh, refresh_hash, refresh_expiry = self._token_issuer.create_refresh_token(
            user_id=user_id,
            tenant_id=tenant_id,
            expires_in_seconds=self._refresh_token_days * 86400,
        )
        await self._repository.store_refresh_token(
            tenant_id, user_id, refresh_hash, refresh_expiry
        )
        return TokenPair(access, refresh)

    @staticmethod
    def _principal(user: AuthUser) -> Principal:
        return Principal(
            user_id=user.id,
            tenant_id=user.tenant_id,
            role=Role(user.role),
            email=user.email,
        )

