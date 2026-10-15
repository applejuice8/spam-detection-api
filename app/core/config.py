from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    database_uri: str
    debug: bool
    jwt_secret: str
    access_token_expires_minutes: int
    refresh_token_expire_days: int
    jwt_algorithm: str

    class Config:
        env_file = '.env'


# Lazy
@lru_cache
def get_settings() -> Settings:
    return Settings()
