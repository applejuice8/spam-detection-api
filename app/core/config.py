from pydantic_settings import BaseSettings, SettingsConfigDict
from functools import lru_cache


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file='.env')

    database_uri: str
    debug: bool
    jwt_secret: str
    access_token_expires_minutes: int
    refresh_token_expire_days: int
    jwt_algorithm: str
    api_key_expire_days: int = 90
    allowed_origins: list[str] = ['http://localhost:3000', 'http://127.0.0.1:5500']


# Lazy
@lru_cache
def get_settings() -> Settings:
    return Settings()
