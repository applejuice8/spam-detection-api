import asyncio
import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.auth.models import APIKey, RefreshToken


logger = logging.getLogger(__name__)

PURGE_INTERVAL_SECONDS = 6 * 3600
# Expired API keys stay listed for a while, so users can see what happened to them
API_KEY_RETENTION = timedelta(days=30)


# Expired refresh tokens can never be used again. Revoked ones are kept until they expire,
# because presenting one is how a stolen token is detected.
async def purge_expired(db: AsyncSession, now: datetime | None = None) -> tuple[int, int]:
    now = now or datetime.now(timezone.utc)
    tokens = await db.execute(delete(RefreshToken).where(RefreshToken.expires_at < now))
    keys = await db.execute(delete(APIKey).where(APIKey.expires_at < now - API_KEY_RETENTION))
    await db.commit()
    return tokens.rowcount, keys.rowcount


# Runs until cancelled. A failed run is logged and retried next interval, it never stops the app.
async def purge_loop(session_maker: async_sessionmaker[AsyncSession], interval: float = PURGE_INTERVAL_SECONDS) -> None:
    while True:
        try:
            async with session_maker() as db:
                tokens, keys = await purge_expired(db)
            logger.info('Purged %d expired refresh tokens and %d expired API keys', tokens, keys)
        except Exception:
            logger.exception('Purging expired tokens failed')
        await asyncio.sleep(interval)
