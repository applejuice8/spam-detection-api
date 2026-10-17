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


# Lazy
@lru_cache
def get_settings() -> Settings:
    return Settings()
