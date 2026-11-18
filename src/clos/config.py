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
    access_token_seconds: int = 900
    refresh_token_days: int = 30
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()
