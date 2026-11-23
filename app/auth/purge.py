import asyncio
import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.auth.models import APIKey, RefreshToken


logger = logging.getLogger(__name__)

PURGE_INTERVAL_SECONDS = 6 * 3600
API_KEY_RETENTION = timedelta(days=30)


# Periodically delete expired refresh tokens
# Revoked tokens are kept until they expire to detect if the token is stolen
async def purge_expired(db: AsyncSession, now: datetime | None = None) -> tuple[int, int]:
    now = now or datetime.now(timezone.utc)
    tokens = await db.execute(delete(RefreshToken).where(RefreshToken.expires_at < now))
    keys = await db.execute(delete(APIKey).where(APIKey.expires_at < now - API_KEY_RETENTION))
    await db.commit()
    return tokens.rowcount, keys.rowcount


# Runs forever, every PURGE_INTERVAL_SECONDS
async def purge_loop(session_maker: async_sessionmaker[AsyncSession], interval: float = PURGE_INTERVAL_SECONDS) -> None:
    while True:
        try:
            async with session_maker() as db:
                tokens, keys = await purge_expired(db)
            logger.info('Purged %d expired refresh tokens and %d expired API keys', tokens, keys)
        except Exception:
            logger.exception('Purging expired tokens failed')
        await asyncio.sleep(interval)
