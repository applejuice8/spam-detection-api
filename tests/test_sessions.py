import asyncio

import pytest
from sqlalchemy import select, func

from app.auth.models import RefreshToken

from .test_auth import bearer


async def login(client, user):
    r = await client.post('/auth/login', data={'username': user['username'], 'password': user['password']})
    assert r.status_code == 200
    return r.json()


async def refresh(client, token):
    return await client.post('/auth/refresh', json={'refresh_token': token})


# ---------- token families ----------
async def test_refreshed_tokens_share_one_family(client, tokens, session_maker):
    r = await refresh(client, tokens['refresh_token'])
    assert r.status_code == 200

    async with session_maker() as s:
        families = set(await s.scalars(select(RefreshToken.family_id)))
    assert len(families) == 1
    assert None not in families


async def test_separate_logins_get_separate_families(client, registered, session_maker):
    await login(client, registered)
    await login(client, registered)

    async with session_maker() as s:
        families = set(await s.scalars(select(RefreshToken.family_id)))
    assert len(families) == 2


async def test_replaying_a_used_refresh_token_revokes_the_whole_family(client, tokens):
    first = await refresh(client, tokens['refresh_token'])
    newest = first.json()['refresh_token']

    replay = await refresh(client, tokens['refresh_token'])
    assert replay.status_code == 401

    # The thief's replay also kills the newest token, so the stolen chain is dead
    assert (await refresh(client, newest)).status_code == 401


async def test_replay_does_not_affect_other_logins(client, registered):
    laptop = await login(client, registered)
    phone = await login(client, registered)

    await refresh(client, laptop['refresh_token'])
    await refresh(client, laptop['refresh_token'])      # replay

    assert (await refresh(client, phone['refresh_token'])).status_code == 200


async def test_logout_revokes_tokens_issued_by_refreshing(client, tokens):
    newest = (await refresh(client, tokens['refresh_token'])).json()['refresh_token']

    out = await client.post('/auth/logout', json={'refresh_token': newest})
    assert out.status_code == 204
    assert (await refresh(client, newest)).status_code == 401


async def test_logout_leaves_other_logins_alone(client, registered):
    laptop = await login(client, registered)
    phone = await login(client, registered)

    await client.post('/auth/logout', json={'refresh_token': laptop['refresh_token']})

    assert (await refresh(client, phone['refresh_token'])).status_code == 200


async def test_legacy_token_without_family_can_still_refresh(client, tokens, session_maker):
    # Tokens issued before families existed have family_id NULL
    async with session_maker() as s:
        row = await s.scalar(select(RefreshToken))
        row.family_id = None
        await s.commit()

    r = await refresh(client, tokens['refresh_token'])
    assert r.status_code == 200
    assert (await refresh(client, tokens['refresh_token'])).status_code == 401


async def test_rotation_is_one_transaction(client, tokens, session_maker, monkeypatch):
    # If storing the new token fails, the old one must stay usable
    import app.auth.service as service

    def boom(*args, **kwargs):
        raise RuntimeError('db write failed')

    monkeypatch.setattr(service, '_new_refresh_row', boom)
    with pytest.raises(RuntimeError):
        await refresh(client, tokens['refresh_token'])
    monkeypatch.undo()

    assert (await refresh(client, tokens['refresh_token'])).status_code == 200


# ---------- log out everywhere ----------
async def test_logout_all_requires_login(client):
    r = await client.post('/auth/logout-all')
    assert r.status_code == 401


async def test_logout_all_revokes_every_refresh_token(client, registered):
    laptop = await login(client, registered)
    phone = await login(client, registered)

    r = await client.post('/auth/logout-all', headers=bearer(laptop['access_token']))
    assert r.status_code == 204

    assert (await refresh(client, laptop['refresh_token'])).status_code == 401
    assert (await refresh(client, phone['refresh_token'])).status_code == 401


async def test_logout_all_invalidates_existing_access_tokens(client, registered):
    laptop = await login(client, registered)
    phone = await login(client, registered)

    await client.post('/auth/logout-all', headers=bearer(laptop['access_token']))

    for t in (laptop, phone):
        r = await client.get('/auth/me', headers=bearer(t['access_token']))
        assert r.status_code == 401
        assert r.json()['detail'] == 'Token revoked'


async def test_login_after_logout_all_works(client, registered):
    first = await login(client, registered)
    await client.post('/auth/logout-all', headers=bearer(first['access_token']))

    # iat has one-second precision: a token minted in the same second as the cutoff is treated as older
    await asyncio.sleep(1.1)
    again = await login(client, registered)

    assert (await client.get('/auth/me', headers=bearer(again['access_token']))).status_code == 200
    assert (await refresh(client, again['refresh_token'])).status_code == 200


async def test_logout_all_does_not_touch_other_users(client, registered):
    other = {'username': 'bob', 'password': 'password456', 'confirm_password': 'password456'}
    await client.post('/auth/signup', json=other)
    bob = await login(client, other)
    alice = await login(client, registered)

    await client.post('/auth/logout-all', headers=bearer(alice['access_token']))

    assert (await client.get('/auth/me', headers=bearer(bob['access_token']))).status_code == 200
    assert (await refresh(client, bob['refresh_token'])).status_code == 200


async def test_tokens_are_not_deleted_by_logout(client, tokens, session_maker):
    # Revoked rows stay until they expire, so replay detection can recognise them
    await client.post('/auth/logout', json={'refresh_token': tokens['refresh_token']})
    async with session_maker() as s:
        assert await s.scalar(select(func.count()).select_from(RefreshToken)) == 1
