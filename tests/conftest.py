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

import json

import joblib
import pytest
import pytest_asyncio
import sklearn
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.naive_bayes import BernoulliNB
from sklearn.pipeline import Pipeline
from redis.exceptions import ConnectionError as RedisConnectionError
from sqlalchemy.pool import StaticPool

import app.models_registry      # Makes sure models registered on Base
from app.db import Base, get_db
from app.main import app
from app.ml_model import SpamClassifier

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


@pytest_asyncio.fixture
async def api_key(client, tokens):
    r = await client.post('/auth/api-keys', json={}, headers={'Authorization': f'Bearer {tokens["access_token"]}'})
    assert r.status_code == 201
    return r.json()['api_key']


# ---------- Fake spam model, so tests need no real ml/models files ----------
@pytest.fixture(scope='session')
def fake_model_dir(tmp_path_factory):
    labels = {'ham': 0, 'spam': 1}    # Same mapping as ml/train.py
    spam = [f'free prize winner claim now call {i}' for i in range(40)]
    ham = [f'see you at lunch tomorrow ok {i}' for i in range(40)]
    y = [labels['spam']] * 40 + [labels['ham']] * 40

    path = tmp_path_factory.mktemp('fake_model')
    pipe = Pipeline([('vec', TfidfVectorizer()), ('model', BernoulliNB())])
    joblib.dump(pipe.fit(spam + ham, y), path / 'spam_detector.pkl')
    (path / 'metadata.json').write_text(json.dumps({
        'f1': 1.0,
        'labels': {str(v): k for k, v in labels.items()},
        'n_train': len(y),
        'sklearn_version': sklearn.__version__,
        'seed': 0,
    }))
    return path


class FakeRedis:
    """In-memory stand-in for the two Redis calls predict uses."""

    def __init__(self):
        self.data = {}

    async def get(self, key):
        return self.data.get(key)

    async def set(self, key, value, ex=None):
        self.data[key] = value


class BrokenRedis:
    """Every call fails, like a Redis server that is down."""

    async def get(self, key):
        raise RedisConnectionError('down')

    async def set(self, key, value, ex=None):
        raise RedisConnectionError('down')


@pytest.fixture
def fake_redis():
    # ASGITransport doesn't run the app lifespan, so set the client by hand
    app.state.redis = FakeRedis()
    yield app.state.redis
    del app.state.redis


@pytest.fixture
def broken_redis(fake_redis):
    # Replaces the fake with one that always fails. fake_redis is listed so its cleanup still runs.
    app.state.redis = BrokenRedis()


@pytest.fixture
def spam_classifier(fake_model_dir, fake_redis):
    # ASGITransport doesn't run the app lifespan, so set the classifier by hand
    app.state.spam_classifier = SpamClassifier(fake_model_dir)
    yield app.state.spam_classifier
    del app.state.spam_classifier
