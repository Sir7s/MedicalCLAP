"""Backend configuration (P1/S4).

Settings are read from environment variables (12-factor). In compose these are
injected per `infra/docker-compose.yml`; locally they fall back to dev defaults.
"""
from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=None, extra="ignore")

    # PostgreSQL
    postgres_host: str = "127.0.0.1"
    postgres_port: int = 5432
    postgres_user: str = "medclip"
    postgres_password: str = "medclip_dev_only"
    postgres_db: str = "medclip"

    # Redis
    redis_host: str = "127.0.0.1"
    redis_port: int = 6379

    # Qdrant
    qdrant_host: str = "127.0.0.1"
    qdrant_port: int = 6333

    # CORS (comma-separated origins)
    backend_cors_origins: str = "http://127.0.0.1:5173,http://localhost:5173"

    # Logging
    log_level: str = "INFO"

    @property
    def cors_origins(self) -> list[str]:
        return [o.strip() for o in self.backend_cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
