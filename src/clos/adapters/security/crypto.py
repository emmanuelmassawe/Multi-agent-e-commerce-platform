"""Password hashing and signed token adapters."""

from datetime import UTC, datetime
from hashlib import sha256
from hmac import new as hmac_new
from secrets import token_urlsafe
from uuid import UUID

import jwt
from pwdlib import PasswordHash

from clos.application.ports import PasswordHasherPort, TokenIssuerPort
from clos.domain.identity import Role


class Argon2PasswordHasher(PasswordHasherPort):
    """Password hashing adapter using pwdlib's Argon2 implementation."""

    def __init__(self) -> None:
        self._hasher = PasswordHash.recommended()

    def hash(self, password: str) -> str:
        return self._hasher.hash(password)

    def verify(self, password: str, password_hash: str) -> bool:
        try:
            return self._hasher.verify(password, password_hash)
        except (ValueError, TypeError):
            return False


class JwtTokenIssuer(TokenIssuerPort):
    """Issue short-lived access JWTs and signed, rotating refresh JWTs."""

    def __init__(self, secret: str, *, issuer: str = "clos", audience: str = "clos-api") -> None:
        if len(secret) < 32:
            raise ValueError("AUTH_JWT_SECRET must contain at least 32 characters")
        self._secret = secret
        self._issuer = issuer
        self._audience = audience

    def create_access_token(
        self, *, user_id: UUID, tenant_id: UUID, role: Role, expires_in_seconds: int
    ) -> str:
        now = int(datetime.now(UTC).timestamp())
        return jwt.encode(
            {
                "sub": str(user_id),
                "tid": str(tenant_id),
                "role": role.value,
                "typ": "access",
                "iat": now,
                "exp": now + expires_in_seconds,
                "iss": self._issuer,
                "aud": self._audience,
            },
            self._secret,
            algorithm="HS256",
        )

    def decode_access_token(self, token: str) -> tuple[UUID, UUID, Role]:
        payload = jwt.decode(
            token,
            self._secret,
            algorithms=["HS256"],
            issuer=self._issuer,
            audience=self._audience,
            options={"require": ["sub", "tid", "role", "typ", "exp"]},
        )
        if payload["typ"] != "access":
            raise jwt.InvalidTokenError("Token is not an access token")
        return UUID(payload["sub"]), UUID(payload["tid"]), Role(payload["role"])

    def create_refresh_token(
        self, *, user_id: UUID, tenant_id: UUID, expires_in_seconds: int
    ) -> tuple[str, str, datetime]:
        now = int(datetime.now(UTC).timestamp())
        expires_at = datetime.fromtimestamp(now + expires_in_seconds, tz=UTC)
        token = jwt.encode(
            {
                "sub": str(user_id),
                "tid": str(tenant_id),
                "jti": token_urlsafe(24),
                "typ": "refresh",
                "iat": now,
                "exp": int(expires_at.timestamp()),
                "iss": self._issuer,
                "aud": self._audience,
            },
            self._secret,
            algorithm="HS256",
        )
        return token, self.hash_refresh_token(token), expires_at

    def hash_refresh_token(self, token: str) -> str:
        return sha256(token.encode("utf-8")).hexdigest()

    def decode_refresh_token(self, token: str) -> tuple[UUID, UUID]:
        payload = jwt.decode(
            token,
            self._secret,
            algorithms=["HS256"],
            issuer=self._issuer,
            audience=self._audience,
            options={"require": ["sub", "tid", "jti", "typ", "exp"]},
        )
        if payload["typ"] != "refresh":
            raise jwt.InvalidTokenError("Token is not a refresh token")
        return UUID(payload["sub"]), UUID(payload["tid"])

    def derive_api_key(self, tenant_id: UUID, idempotency_key: str) -> tuple[str, str]:
        """Derive stable secret material so a retried idempotent request returns one key."""
        message = f"{tenant_id}:{idempotency_key}".encode("utf-8")
        prefix = hmac_new(self._secret.encode(), b"clos-prefix:" + message, sha256).hexdigest()[:12]
        secret = hmac_new(self._secret.encode(), b"clos-secret:" + message, sha256).hexdigest()
        return prefix, f"clos.{tenant_id}.{prefix}_{secret}.v1"

