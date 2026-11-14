import pytest

from app.core import rate_limit
from app.core.cache import RedisGuard

from .conftest import USER
from .test_auth import bearer


async def login(client, password='password123'):
    return await client.post('/auth/login', data={'username': 'alice', 'password': password})


async def test_login_is_limited_per_ip(client, registered):
    limit, _ = rate_limit.LIMITS['login']
    for _ in range(limit):
        assert (await login(client, 'wrong-password')).status_code == 401

    r = await login(client, 'wrong-password')
    assert r.status_code == 429
    assert r.headers['retry-after'] == str(rate_limit.LIMITS['login'][1])


async def test_limit_blocks_correct_password_too(client, registered):
    # Otherwise a guesser could keep going and just watch for the one request that isn't 429
    limit, _ = rate_limit.LIMITS['login']
    for _ in range(limit):
        await login(client, 'wrong-password')
    assert (await login(client)).status_code == 429


async def test_limit_resets_with_the_next_window(client, registered, fake_redis):
    limit, _ = rate_limit.LIMITS['login']
    for _ in range(limit + 1):
        await login(client, 'wrong-password')
    assert (await login(client)).status_code == 429

    fake_redis.reset_windows()
    assert (await login(client)).status_code == 200


async def test_signup_is_limited(client):
    limit, _ = rate_limit.LIMITS['signup']
    for i in range(limit):
        r = await client.post('/auth/signup', json={**USER, 'username': f'user{i}'})
        assert r.status_code == 201
    r = await client.post('/auth/signup', json={**USER, 'username': 'onetoomany'})
    assert r.status_code == 429


async def test_refresh_is_limited(client):
    limit, _ = rate_limit.LIMITS['refresh']
    for _ in range(limit):
        assert (await client.post('/auth/refresh', json={'refresh_token': 'x'})).status_code == 401
    assert (await client.post('/auth/refresh', json={'refresh_token': 'x'})).status_code == 429


async def test_window_is_set_once_per_key(client, registered, fake_redis):
    # expire(nx=True): later requests must not push the window out, or a steady trickle would never reset
    await login(client)
    await login(client)
    (key,) = [k for k in fake_redis.ttls if k.startswith('rl:login:')]
    assert fake_redis.ttls[key] == rate_limit.LIMITS['login'][1]
    assert fake_redis.counters[key] == 2


async def test_limits_are_kept_per_ip(client, registered, fake_redis):
    limit, _ = rate_limit.LIMITS['login']
    for _ in range(limit + 1):
        await login(client, 'wrong-password')

    # Another client address has its own counter
    fake_redis.counters = {k: v for k, v in fake_redis.counters.items() if '127.0.0.1' not in k}
    assert (await login(client)).status_code == 200


async def test_requests_still_work_when_redis_is_down(client, registered, broken_redis):
    # Fail open: an outage of the limiter must not lock everyone out
    for _ in range(rate_limit.LIMITS['login'][0] + 5):
        assert (await login(client)).status_code == 200


# ---------- predict ----------
async def test_predict_is_limited_per_user(client, spam_classifier, api_key, monkeypatch):
    monkeypatch.setitem(rate_limit.LIMITS, 'predict_user', (3, 60))
    headers = {'X-API-Key': api_key}
    for _ in range(3):
        assert (await client.post('/predict', json={'text': 'hello'}, headers=headers)).status_code == 200
    assert (await client.post('/predict', json={'text': 'hello'}, headers=headers)).status_code == 429


async def test_predict_user_limit_does_not_affect_other_users(client, spam_classifier, api_key, monkeypatch):
    monkeypatch.setitem(rate_limit.LIMITS, 'predict_user', (2, 60))
    await client.post('/auth/signup', json={**USER, 'username': 'bob'})
    bob_login = await client.post('/auth/login', data={'username': 'bob', 'password': USER['password']})
    bob_key = (await client.post('/auth/api-keys', json={}, headers=bearer(bob_login.json()['access_token']))).json()['api_key']

    for _ in range(2):
        await client.post('/predict', json={'text': 'hello'}, headers={'X-API-Key': api_key})
    assert (await client.post('/predict', json={'text': 'hello'}, headers={'X-API-Key': api_key})).status_code == 429
    assert (await client.post('/predict', json={'text': 'hello'}, headers={'X-API-Key': bob_key})).status_code == 200


async def test_ip_limit_applies_before_the_api_key_check(client, spam_classifier, monkeypatch):
    monkeypatch.setitem(rate_limit.LIMITS, 'predict_ip', (2, 60))
    bad = {'X-API-Key': 'sk_guess'}
    codes = [(await client.post('/predict', json={'text': 'hi'}, headers=bad)).status_code for _ in range(4)]
    assert codes == [401, 401, 429, 429]


async def test_rate_limit_is_counted_in_metrics(client, registered):
    from app.core.metrics import RATE_LIMITED

    before = RATE_LIMITED.labels(scope='login')._value.get()
    for _ in range(rate_limit.LIMITS['login'][0] + 2):
        await login(client, 'wrong-password')
    assert RATE_LIMITED.labels(scope='login')._value.get() == before + 2


# ---------- RedisGuard.count ----------
@pytest.mark.parametrize('n', [1, 5])
async def test_count_returns_running_total(fake_redis, n):
    guard = RedisGuard(fake_redis)
    total = [await guard.count('k', 60) for _ in range(n)]
    assert total == list(range(1, n + 1))
