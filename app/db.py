from collections.abc import AsyncGenerator
from app.core.config import get_settings
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncAttrs, AsyncSession

engine = create_async_engine(
    get_settings().database_uri,
    pool_pre_ping=True,
    echo=get_settings().debug
)

async_session = async_sessionmaker(
    bind=engine,
    expire_on_commit=False,
    autoflush=False
)

class Base(AsyncAttrs, DeclarativeBase):
    pass

async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with async_session() as session:
        yield session
