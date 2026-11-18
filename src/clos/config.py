"""Application settings loaded from environment variables."""

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_env: str = "production"
    log_level: str = "INFO"
    database_url: str | None = None
    database_admin_url: str | None = None
    rabbitmq_url: str | None = None
    auth_jwt_secret: SecretStr | None = None
    gemini_api_key: SecretStr | None = None
    gemini_fallback_api_keys: SecretStr | None = None
    gemini_model: str = "gemini-3.8-flash"
    gemini_fallback_model: str = "gemini-3.6-flash"
    access_token_seconds: int = 900
    refresh_token_days: int = 30
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()
