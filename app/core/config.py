from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from functools import lru_cache


MIN_JWT_SECRET_LENGTH = 32


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file='.env', extra='ignore')

    database_uri: str
    jwt_secret: str
    access_token_expires_minutes: int
    refresh_token_expire_days: int
    sql_echo: bool = False
    metrics_host: str = '127.0.0.1'
    metrics_port: int = 9100
    metrics_bearer_token: str = ''
    spam_threshold: float = Field(default=0.5, gt=0, lt=1)
    redis_url: str = 'redis://localhost:6379/0'
    allowed_origins: list[str] = [
        'http://localhost:3000',
        'http://localhost:5500',
        'http://127.0.0.1:5500',
    ]

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
