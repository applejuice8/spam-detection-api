from datetime import datetime, timedelta, timezone

import jwt
import pytest
from sqlalchemy import select, update

from app.auth.models import RefreshToken, User
from app.core.config import get_settings
from app.core.security import JWT_ALGORITHM, fast_hash

from .conftest import USER


def make_jwt(secret=None, **overrides):
    """Build an access token; pass key=None to drop that claim."""
    now = datetime.now(timezone.utc)
    payload = {
        'sub': '1', 'iat': now, 'exp': now + timedelta(minutes=5),
        'type': 'access', **overrides,
    }
    payload = {k: v for k, v in payload.items() if v is not None}
    s = get_settings()
    return jwt.encode(payload, secret or s.jwt_secret, algorithm=JWT_ALGORITHM)


def bearer(token):
    return {'Authorization': f'Bearer {token}'}


# ---------- signup ----------

async def test_signup_success(client):
    r = await client.post('/auth/signup', json=USER)
    assert r.status_code == 201
    body = r.json()
    assert body['username'] == 'alice'
    assert 'password' not in body


async def test_signup_duplicate_username(client, registered):
    r = await client.post('/auth/signup', json=USER)
    assert r.status_code == 409


async def test_signup_password_mismatch(client):
    r = await client.post('/auth/signup', json={**USER, 'confirm_password': 'different123'})
    assert r.status_code == 422


@pytest.mark.parametrize('override', [
    {'password': 'short', 'confirm_password': 'short'},
    {'username': 'a' * 21},
    {'username': 'ab'},
    {'password': 'x' * 129, 'confirm_password': 'x' * 129},
], ids=['short-password', 'long-username', 'short-username', 'long-password'])
async def test_signup_validation(client, override):
    r = await client.post('/auth/signup', json={**USER, **override})
    assert r.status_code == 422


async def test_password_is_stored_hashed(client, registered, session_maker):
    async with session_maker() as s:
        stored = await s.scalar(select(User.password))
    assert stored != USER['password']
    assert stored.startswith('$argon2')


# ---------- login ----------

async def test_login_success(tokens):
    assert tokens['token_type'] == 'bearer'
    assert tokens['access_token']
    assert tokens['refresh_token']


async def test_login_wrong_password(client, registered):
    r = await client.post('/auth/login', data={'username': 'alice', 'password': 'wrongpass1'})
    assert r.status_code == 401
    assert r.headers['www-authenticate'] == 'Bearer'


async def test_login_unknown_user_same_error_as_wrong_password(client, registered):
    wrong_pw = await client.post('/auth/login', data={'username': 'alice', 'password': 'wrongpass1'})
    no_user = await client.post('/auth/login', data={'username': 'nobody', 'password': 'wrongpass1'})
    assert no_user.status_code == wrong_pw.status_code == 401
    assert no_user.json() == wrong_pw.json()


async def test_login_rejects_json_body(client, registered):
    # login is form-based now (needed for Swagger's Authorize button)
    r = await client.post('/auth/login', json={'username': 'alice', 'password': 'password123'})
    assert r.status_code == 422


# ---------- /me ----------

async def test_me_with_valid_token(client, tokens):
    r = await client.get('/auth/me', headers=bearer(tokens['access_token']))
    assert r.status_code == 200
    assert r.json()['username'] == 'alice'


async def test_me_without_token(client):
    r = await client.get('/auth/me')
    assert r.status_code == 401


async def test_me_garbage_token(client):
    r = await client.get('/auth/me', headers=bearer('abc.def.ghi'))
    assert r.status_code == 401
    assert r.headers['www-authenticate'] == 'Bearer'


async def test_me_expired_token(client, registered):
    token = make_jwt(exp=datetime.now(timezone.utc) - timedelta(minutes=1))
    r = await client.get('/auth/me', headers=bearer(token))
    assert r.status_code == 401
    assert r.json()['detail'] == 'Token expired'


async def test_me_wrong_signature(client, registered):
    r = await client.get('/auth/me', headers=bearer(make_jwt(secret='another-secret-another-secret-12345')))
    assert r.status_code == 401


@pytest.mark.parametrize('overrides', [
    {'type': 'refresh'},
    {'type': None},
    {'sub': None},
    {'sub': 'not-a-number'},
    {'exp': None},
], ids=['wrong-type', 'missing-type', 'missing-sub', 'non-numeric-sub', 'missing-exp'])
async def test_me_malformed_claims(client, registered, overrides):
    r = await client.get('/auth/me', headers=bearer(make_jwt(**overrides)))
    assert r.status_code == 401


async def test_me_token_for_nonexistent_user(client, registered):
    r = await client.get('/auth/me', headers=bearer(make_jwt(sub='9999')))
    assert r.status_code == 401
    assert r.json()['detail'] == 'User not found'


# ---------- refresh ----------

async def test_refresh_returns_new_token_pair(client, tokens):
    r = await client.post('/auth/refresh', json={'refresh_token': tokens['refresh_token']})
    assert r.status_code == 200
    body = r.json()
    # fails if /refresh still has response_model=AccessTokenOut
    assert 'refresh_token' in body
    assert body['refresh_token'] != tokens['refresh_token']
    # not asserting the access token differs: iat/exp are whole seconds,
    # so two tokens made in the same second are identical

    me = await client.get('/auth/me', headers=bearer(body['access_token']))
    assert me.status_code == 200


async def test_refresh_token_is_single_use(client, tokens):
    old = tokens['refresh_token']
    first = await client.post('/auth/refresh', json={'refresh_token': old})
    second = await client.post('/auth/refresh', json={'refresh_token': old})
    assert first.status_code == 200
    assert second.status_code == 401


async def test_rotated_refresh_token_works(client, tokens):
    first = await client.post('/auth/refresh', json={'refresh_token': tokens['refresh_token']})
    second = await client.post('/auth/refresh', json={'refresh_token': first.json()['refresh_token']})
    assert second.status_code == 200


async def test_refresh_unknown_token(client):
    r = await client.post('/auth/refresh', json={'refresh_token': 'does-not-exist'})
    assert r.status_code == 401
    assert r.headers['www-authenticate'] == 'Bearer'


async def test_refresh_expired_token(client, tokens, session_maker):
    async with session_maker() as s:
        await s.execute(update(RefreshToken).values(
            expires_at=datetime.now(timezone.utc) - timedelta(days=1)))
        await s.commit()
    r = await client.post('/auth/refresh', json={'refresh_token': tokens['refresh_token']})
    assert r.status_code == 401


async def test_refresh_token_is_stored_hashed(tokens, session_maker):
    async with session_maker() as s:
        stored = await s.scalar(select(RefreshToken.token))
    assert stored != tokens['refresh_token']
    assert stored == fast_hash(tokens['refresh_token'])


# ---------- logout ----------

async def test_logout_revokes_refresh_token(client, tokens):
    out = await client.post('/auth/logout', json={'refresh_token': tokens['refresh_token']})
    assert out.status_code == 204
    r = await client.post('/auth/refresh', json={'refresh_token': tokens['refresh_token']})
    assert r.status_code == 401


async def test_logout_with_unknown_token_still_204(client):
    r = await client.post('/auth/logout', json={'refresh_token': 'nope'})
    assert r.status_code == 204