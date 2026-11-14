from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from functools import lru_cache


MIN_JWT_SECRET_LENGTH = 32


class Settings(BaseSettings):
    # extra='ignore': .env is shared with docker compose (GRAFANA_ADMIN_PASSWORD, ...),
    # and keys this app doesn't read must not stop it from starting
    model_config = SettingsConfigDict(env_file='.env', extra='ignore')

    database_uri: str
    jwt_secret: str
    access_token_expires_minutes: int
    refresh_token_expire_days: int
    sql_echo: bool = False      # Log every SQL statement with its parameters. Never enable in production.
    redis_url: str = 'redis://localhost:6379/0'
    allowed_origins: list[str] = ['http://localhost:3000', 'http://127.0.0.1:5500']

    @field_validator('jwt_secret')
    @classmethod
    def jwt_secret_is_strong(cls, v: str) -> str:
        if len(v) < MIN_JWT_SECRET_LENGTH:
            raise ValueError(
                f'JWT_SECRET must be at least {MIN_JWT_SECRET_LENGTH} characters. Generate one with: openssl rand -hex 32'
            )
        return v


# Lazy
@lru_cache
def get_settings() -> Settings:
    return Settings()
