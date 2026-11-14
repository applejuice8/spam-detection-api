import asyncio
from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from app.auth.maintenance import API_KEY_RETENTION, purge_expired, purge_loop
from app.auth.models import APIKey, RefreshToken

from .test_auth import bearer


async def test_purge_removes_only_expired_refresh_tokens(client, tokens, registered, session_maker):
    now = datetime.now(timezone.utc)
    async with session_maker() as s:
        live = await s.scalar(select(RefreshToken))
        s.add(RefreshToken(user_id=live.user_id, token='expired', expires_at=now - timedelta(minutes=1)))
        s.add(RefreshToken(user_id=live.user_id, token='revoked-but-live', revoked=True, expires_at=now + timedelta(days=1)))
        await s.commit()

    async with session_maker() as s:
        deleted_tokens, _ = await purge_expired(s)

    async with session_maker() as s:
        remaining = set(await s.scalars(select(RefreshToken.token)))
    assert deleted_tokens == 1
    assert 'expired' not in remaining
    assert 'revoked-but-live' in remaining       # needed for replay detection
    assert len(remaining) == 2


async def test_purge_keeps_recently_expired_api_keys(client, tokens, session_maker):
    for days in (7, 30):
        await client.post('/auth/api-keys', json={'expires_in_days': days}, headers=bearer(tokens['access_token']))

    # Pretend time has passed: 8 days is past the first key's expiry but inside the retention window
    async with session_maker() as s:
        deleted = await purge_expired(s, now=datetime.now(timezone.utc) + timedelta(days=8))
    assert deleted[1] == 0

    # Past retention for the 7 day key only
    later = datetime.now(timezone.utc) + timedelta(days=7) + API_KEY_RETENTION + timedelta(hours=1)
    async with session_maker() as s:
        deleted = await purge_expired(s, now=later)
    assert deleted[1] == 1
    async with session_maker() as s:
        assert len(list(await s.scalars(select(APIKey)))) == 1


async def test_purge_loop_survives_a_failing_run(caplog):
    calls = 0

    class BrokenSession:
        async def __aenter__(self):
            nonlocal calls
            calls += 1
            raise RuntimeError('db down')

        async def __aexit__(self, *exc):
            return False

    task = asyncio.create_task(purge_loop(lambda: BrokenSession(), interval=0.01))
    await asyncio.sleep(0.1)
    task.cancel()

    assert calls >= 2           # kept going after the first failure
    assert 'Purging expired tokens failed' in caplog.text
