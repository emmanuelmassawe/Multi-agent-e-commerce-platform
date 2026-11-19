"""Application settings loaded from environment variables."""

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_env: str = "production"
    log_level: str = "INFO"
    database_url: str | None = None
    database_admin_url: str | None = None
    rabbitmq_url: str | None = None
    qdrant_url: str = "http://localhost:6333"
    qdrant_collection: str = "clos_memory_v1"
    redis_url: str = "redis://localhost:6379/0"
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
