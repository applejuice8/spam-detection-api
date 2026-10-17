import os

# MUST come before importing anything from your app, because db.py and
# security.py call get_settings() at import time. Real env vars beat .env,
# so this also guarantees tests can never touch your dev database.
os.environ.update({
    'DATABASE_URI': 'sqlite+aiosqlite://',
    'DEBUG': 'false',
    'JWT_SECRET': 'test-secret-test-secret-test-secret-123',
    'JWT_ALGORITHM': 'HS256',
    'ACCESS_TOKEN_EXPIRES_MINUTES': '15',
    'REFRESH_TOKEN_EXPIRE_DAYS': '7',
})

import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

import app.models_registry      # Makes sure models registered on Base
from app.db import Base, get_db
from app.main import app

USER = {
    'username': 'alice',
    'password': 'password123',
    'confirm_password': 'password123',
}


@pytest_asyncio.fixture
async def session_maker():
    # StaticPool = one shared connection, so the in-memory DB survives across sessions
    engine = create_async_engine('sqlite+aiosqlite://', poolclass=StaticPool)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield async_sessionmaker(engine, expire_on_commit=False, autoflush=False)
    await engine.dispose()  # fresh empty DB for every test


@pytest_asyncio.fixture
async def client(session_maker):
    async def override_get_db():
        async with session_maker() as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db
    async with AsyncClient(transport=ASGITransport(app=app), base_url='http://test') as c:
        yield c
    app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def registered(client):
    r = await client.post('/auth/signup', json=USER)
    assert r.status_code == 201
    return USER


@pytest_asyncio.fixture
async def tokens(client, registered):
    r = await client.post('/auth/login', data={
        'username': registered['username'],
        'password': registered['password'],
    })
    assert r.status_code == 200
    return r.json()
