import os

# MUST come before importing anything from your app, because db.py and
# security.py call get_settings() at import time. Real env vars beat .env,
# so this also guarantees tests can never touch your dev database.
os.environ.update({
    'DATABASE_URI': 'sqlite+aiosqlite://',
    'JWT_SECRET': 'test-secret-test-secret-test-secret-123',
    'ACCESS_TOKEN_EXPIRES_MINUTES': '15',
    'REFRESH_TOKEN_EXPIRE_DAYS': '7',
    'METRICS_PORT': '0',        # Any free port, so tests never clash with a running dev server
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
from app.core.cache import RedisGuard
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
async def client(session_maker, fake_redis):
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


class FakePipeline:
    def __init__(self, redis):
        self.redis = redis
        self.ops = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    def incr(self, key):
        self.ops.append(('incr', key))
        return self

    def expire(self, key, seconds, nx=False):
        self.ops.append(('expire', key, seconds, nx))
        return self

    async def execute(self):
        if self.redis.broken:
            raise RedisConnectionError('down')
        results = []
        for op, key, *rest in self.ops:
            if op == 'incr':
                self.redis.counters[key] = self.redis.counters.get(key, 0) + 1
                results.append(self.redis.counters[key])
            else:
                seconds, nx = rest
                if not (nx and key in self.redis.ttls):
                    self.redis.ttls[key] = seconds
                results.append(True)
        return results


class FakeRedis:
    """In-memory stand-in for the Redis calls the app uses. broken=True makes every call fail, like a Redis that is down."""

    def __init__(self, broken=False):
        self.data = {}
        self.counters = {}
        self.ttls = {}
        self.broken = broken
        self.calls = 0

    def _call(self):
        self.calls += 1
        if self.broken:
            raise RedisConnectionError('down')

    async def get(self, key):
        self._call()
        return self.data.get(key)

    async def set(self, key, value, ex=None):
        self._call()
        self.data[key] = value

    def pipeline(self, transaction=True):
        self.calls += 1
        return FakePipeline(self)

    def reset_windows(self):
        """Pretend every rate limit window has passed."""
        self.counters.clear()
        self.ttls.clear()


@pytest.fixture
def fake_redis():
    # ASGITransport doesn't run the app lifespan, so set the cache by hand
    fake = FakeRedis()
    app.state.cache = RedisGuard(fake)
    yield fake
    del app.state.cache


@pytest.fixture
def broken_redis(fake_redis):
    # Makes the fake fail on every call. fake_redis is listed so its cleanup still runs.
    fake_redis.broken = True
    return fake_redis


@pytest.fixture
def spam_classifier(fake_model_dir, fake_redis):
    # ASGITransport doesn't run the app lifespan, so set the classifier by hand
    app.state.spam_classifier = SpamClassifier(fake_model_dir)
    yield app.state.spam_classifier
    del app.state.spam_classifier
