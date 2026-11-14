from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select, update

from app.auth.models import APIKey
from app.core.security import fast_hash

from .test_auth import bearer

BOB = {'username': 'bob', 'password': 'password456', 'confirm_password': 'password456'}


async def create_key(client, access_token, **body):
    return await client.post('/auth/api-keys', json=body, headers=bearer(access_token))


@pytest.fixture
async def bob_tokens(client, registered):
    await client.post('/auth/signup', json=BOB)
    r = await client.post('/auth/login', data={'username': BOB['username'], 'password': BOB['password']})
    return r.json()


# ---------- create ----------
async def test_create_key_returns_raw_key_once(client, tokens):
    r = await create_key(client, tokens['access_token'])
    assert r.status_code == 201
    body = r.json()
    assert body['api_key'].startswith('sk_')
    assert body['prefix'] == body['api_key'][:9]
    assert body['revoked'] is False

    listed = await client.get('/auth/api-keys', headers=bearer(tokens['access_token']))
    assert 'api_key' not in listed.json()[0]


async def test_create_key_defaults_to_90_days(client, tokens):
    body = (await create_key(client, tokens['access_token'])).json()
    expires = datetime.fromisoformat(body['expires_at'])
    created = datetime.fromisoformat(body['created_at'])
    assert abs((expires - created).days - 90) <= 1


@pytest.mark.parametrize('days', [7, 30, 90, 180, 365])
async def test_create_key_accepts_listed_lifetimes(client, tokens, days):
    assert (await create_key(client, tokens['access_token'], expires_in_days=days)).status_code == 201


@pytest.mark.parametrize('days', [0, -1, 1, 366, 10_000, 'forever'])
async def test_create_key_rejects_other_lifetimes(client, tokens, days):
    assert (await create_key(client, tokens['access_token'], expires_in_days=days)).status_code == 422


async def test_create_key_requires_login(client):
    r = await client.post('/auth/api-keys', json={})
    assert r.status_code == 401


async def test_key_is_stored_hashed(client, tokens, session_maker):
    raw = (await create_key(client, tokens['access_token'])).json()['api_key']
    async with session_maker() as s:
        stored = await s.scalar(select(APIKey.key_hash))
    assert stored == fast_hash(raw)
    assert raw not in stored


# ---------- list ----------
async def test_list_returns_only_own_keys(client, tokens, bob_tokens):
    await create_key(client, tokens['access_token'])
    await create_key(client, bob_tokens['access_token'])
    await create_key(client, bob_tokens['access_token'])

    mine = await client.get('/auth/api-keys', headers=bearer(tokens['access_token']))
    bobs = await client.get('/auth/api-keys', headers=bearer(bob_tokens['access_token']))
    assert len(mine.json()) == 1
    assert len(bobs.json()) == 2


async def test_list_requires_login(client):
    assert (await client.get('/auth/api-keys')).status_code == 401


# ---------- revoke ----------
async def test_revoke_key_then_it_stops_working(client, tokens, spam_classifier):
    created = (await create_key(client, tokens['access_token'])).json()
    headers = {'X-API-Key': created['api_key']}
    assert (await client.post('/predict', json={'text': 'hello'}, headers=headers)).status_code == 200

    r = await client.delete(f'/auth/api-keys/{created["id"]}', headers=bearer(tokens['access_token']))
    assert r.status_code == 204

    assert (await client.post('/predict', json={'text': 'hello'}, headers=headers)).status_code == 401
    listed = await client.get('/auth/api-keys', headers=bearer(tokens['access_token']))
    assert listed.json()[0]['revoked'] is True


async def test_cannot_revoke_another_users_key(client, tokens, bob_tokens, spam_classifier):
    created = (await create_key(client, tokens['access_token'])).json()

    r = await client.delete(f'/auth/api-keys/{created["id"]}', headers=bearer(bob_tokens['access_token']))
    assert r.status_code == 404         # Same answer as a missing key, so ids can't be probed

    headers = {'X-API-Key': created['api_key']}
    assert (await client.post('/predict', json={'text': 'hello'}, headers=headers)).status_code == 200


async def test_revoke_unknown_key_is_404(client, tokens):
    r = await client.delete('/auth/api-keys/9999', headers=bearer(tokens['access_token']))
    assert r.status_code == 404


async def test_revoking_twice_is_404(client, tokens):
    key_id = (await create_key(client, tokens['access_token'])).json()['id']
    first = await client.delete(f'/auth/api-keys/{key_id}', headers=bearer(tokens['access_token']))
    second = await client.delete(f'/auth/api-keys/{key_id}', headers=bearer(tokens['access_token']))
    assert (first.status_code, second.status_code) == (204, 404)


async def test_revoke_requires_login(client):
    assert (await client.delete('/auth/api-keys/1')).status_code == 401


# ---------- using keys ----------
async def test_expired_key_is_rejected(client, tokens, session_maker, spam_classifier):
    raw = (await create_key(client, tokens['access_token'])).json()['api_key']
    async with session_maker() as s:
        await s.execute(update(APIKey).values(expires_at=datetime.now(timezone.utc) - timedelta(seconds=1)))
        await s.commit()

    r = await client.post('/predict', json={'text': 'hello'}, headers={'X-API-Key': raw})
    assert r.status_code == 401
    assert r.headers['www-authenticate'] == 'APIKey'


async def test_key_works_for_its_owner_only_through_the_header(client, api_key, spam_classifier):
    # A key is not a login token
    assert (await client.get('/auth/me', headers=bearer(api_key))).status_code == 401
    # And a login token is not a key
    assert (await client.post('/predict', json={'text': 'hi'}, headers={'X-API-Key': 'x'})).status_code == 401


async def test_rejections_are_counted(client, spam_classifier):
    from app.core.metrics import API_KEY_REJECTIONS

    def count(reason):
        return API_KEY_REJECTIONS.labels(reason=reason)._value.get()

    missing, invalid = count('missing'), count('invalid')
    await client.post('/predict', json={'text': 'hi'})
    await client.post('/predict', json={'text': 'hi'}, headers={'X-API-Key': 'sk_nope'})

    assert count('missing') == missing + 1
    assert count('invalid') == invalid + 1

