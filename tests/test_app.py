import urllib.request

import pytest
from fastapi.testclient import TestClient

import app.main as main
from app.ml_model import SpamClassifier


@pytest.fixture
def running_app(fake_model_dir, monkeypatch):
    """The real app with its lifespan (startup and shutdown) running, using the fake model."""
    monkeypatch.setattr(main, 'SpamClassifier', lambda threshold: SpamClassifier(fake_model_dir, threshold))
    with TestClient(main.app) as c:
        yield c


def fetch(url):
    with urllib.request.urlopen(url, timeout=3) as r:
        return r.status, r.read().decode()


# ---------- lifespan ----------
def test_startup_loads_model_cache_and_metrics_server(running_app):
    state = main.app.state
    assert state.spam_classifier.version
    assert state.cache is not None
    assert state.metrics_server.server_port > 0


def test_metrics_are_served_on_their_own_port(running_app):
    port = main.app.state.metrics_server.server_port
    running_app.get('/health')

    status, body = fetch(f'http://127.0.0.1:{port}/metrics')
    assert status == 200
    assert 'http_requests_total' in body
    assert 'spam_model_f1' in body


def test_metrics_are_served_on_the_api_port(running_app):
    running_app.get('/health')

    response = running_app.get('/metrics')
    assert response.status_code == 200
    assert 'http_requests_total' in response.text
    assert 'spam_model_f1' in response.text


def test_shutdown_stops_the_metrics_server(fake_model_dir, monkeypatch):
    monkeypatch.setattr(main, 'SpamClassifier', lambda threshold: SpamClassifier(fake_model_dir, threshold))
    with TestClient(main.app):
        port = main.app.state.metrics_server.server_port
        fetch(f'http://127.0.0.1:{port}/metrics')

    with pytest.raises(OSError):
        fetch(f'http://127.0.0.1:{port}/metrics')


def test_startup_survives_a_failing_purge(running_app):
    # The test database has no tables, so the first purge fails. The app must keep serving.
    assert running_app.get('/health').status_code == 200


# ---------- health ----------
async def test_health_is_always_ok(client):
    r = await client.get('/health')
    assert (r.status_code, r.json()) == (200, {'status': 'ok'})


async def test_ready_when_model_and_database_are_up(client, spam_classifier):
    r = await client.get('/ready')
    assert (r.status_code, r.json()) == (200, {'status': 'ready'})


async def test_not_ready_without_a_model(client):
    r = await client.get('/ready')
    assert r.status_code == 503
    assert r.json()['detail'] == 'Model not loaded'


async def test_not_ready_when_database_is_down(client, spam_classifier):
    from app.db import get_db

    class BrokenSession:
        async def execute(self, *args, **kwargs):
            raise ConnectionError('db down')

    async def broken_db():
        yield BrokenSession()

    main.app.dependency_overrides[get_db] = broken_db
    r = await client.get('/ready')
    assert r.status_code == 503
    assert r.json()['detail'] == 'Database unavailable'
