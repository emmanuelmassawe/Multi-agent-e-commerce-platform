"""Application settings loaded from environment variables."""

from uuid import UUID

from pydantic import BaseModel, Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class IntegrationBinding(BaseModel):
    shopify_secret: SecretStr | None = None
    carrier_secret: SecretStr | None = None
    outbound_url: str | None = None
    outbound_secret: SecretStr | None = None
    price_feed_url: str | None = None
    tracking_feed_url: str | None = None
    feed_token: SecretStr | None = None
    inventory_interval_seconds: int | None = Field(None,ge=60)
    pricing_interval_seconds: int | None = Field(None,ge=60)
    logistics_interval_seconds: int | None = Field(None,ge=60)

    @field_validator("outbound_url","price_feed_url","tracking_feed_url")
    @classmethod
    def require_https(cls,value: str | None) -> str | None:
        if value is not None and not value.startswith("https://"):
            raise ValueError("Integration destination must use HTTPS")
        return value


class Settings(BaseSettings):
    app_env: str = "production"
    log_level: str = "INFO"
    database_url: str | None = None
    database_admin_url: str | None = None
    rabbitmq_url: str | None = None
    qdrant_url: str = "http://localhost:6333"
    qdrant_collection: str = "clos_memory_v1"
    redis_url: str = "redis://localhost:6379/0"
    integrations: dict[UUID,IntegrationBinding] = Field(default_factory=dict)
    tenant_requests_per_minute: int = Field(240,ge=1)
    user_requests_per_minute: int = Field(60,ge=1)
    delivery_max_attempts: int = Field(5,ge=1,le=20)

    @field_validator("integrations")
    @classmethod
    def distinct_credentials(cls,bindings: dict[UUID,IntegrationBinding]) -> dict[UUID,IntegrationBinding]:
        seen: set[str] = set()
        for binding in bindings.values():
            for key in (binding.shopify_secret,binding.carrier_secret,binding.outbound_secret):
                if key is not None:
                    secret = key.get_secret_value()
                    if len(secret)<16 or secret in seen:
                        raise ValueError("Integration secrets must be distinct and at least 16 characters")
                    seen.add(secret)
            if bool(binding.outbound_url) != bool(binding.outbound_secret):
                raise ValueError("Outbound destination and signing secret must be configured together")
        return bindings
    auth_jwt_secret: SecretStr | None = None
    gemini_api_key: SecretStr | None = None
    gemini_fallback_api_keys: SecretStr | None = None
    gemini_model: str = "gemini-3.8-flash"
    gemini_fallback_model: str = "gemini-3.6-flash"
    access_token_seconds: int = 900
    refresh_token_days: int = 30
    approval_expiry_seconds: int | None = Field(default=None, ge=1)
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()
