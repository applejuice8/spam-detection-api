from collections.abc import AsyncGenerator
from app.core.config import get_settings
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncAttrs, AsyncSession
from fastapi import Depends
from typing import Annotated


settings = get_settings()


engine = create_async_engine(
    settings.database_uri,
    pool_pre_ping=True,
    echo=settings.sql_echo
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


DBDep = Annotated[AsyncSession, Depends(get_db)]
