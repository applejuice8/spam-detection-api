import time
from collections.abc import Callable
from typing import Annotated

from fastapi import Depends, Request
from redis.asyncio import Redis
from redis.exceptions import RedisError


class CacheUnavailable(Exception):
    """Redis is down, or was recently seen failing and is being skipped."""


# Redis is optional: callers carry on without it. After one failure it is skipped for `cooldown` seconds,
# so a dead Redis costs one slow request (the client's socket timeout), not one per Redis call.
class RedisGuard:
    def __init__(self, redis: Redis, cooldown: float = 30.0, clock: Callable[[], float] = time.monotonic):
        self.redis = redis
        self.cooldown = cooldown
        self._clock = clock
        self._down_until = 0.0

    def _check(self) -> None:
        if self._clock() < self._down_until:
            raise CacheUnavailable('Redis is being skipped after a recent failure')

    def _trip(self) -> None:
        self._down_until = self._clock() + self.cooldown

    async def get(self, key: str) -> str | None:
        self._check()
        try:
            return await self.redis.get(key)
        except RedisError as e:
            self._trip()
            raise CacheUnavailable('Redis get failed') from e

    # Best effort: a failed write is not an error for the caller
    async def set(self, key: str, value: str, ex: int) -> None:
        try:
            self._check()
            await self.redis.set(key, value, ex=ex)
        except CacheUnavailable:
            pass
        except RedisError:
            self._trip()

    # Fixed window counter. Returns how many times `key` was counted in the current window.
    # The expiry is set atomically with the increment, so a crash can't leave a counter that never resets.
    async def count(self, key: str, window_seconds: int) -> int:
        self._check()
        try:
            async with self.redis.pipeline(transaction=True) as pipe:
                pipe.incr(key)
                pipe.expire(key, window_seconds, nx=True)
                count, _ = await pipe.execute()
            return count
        except RedisError as e:
            self._trip()
            raise CacheUnavailable('Redis count failed') from e

    async def aclose(self) -> None:
        await self.redis.aclose()


def get_cache(req: Request) -> RedisGuard:
    return req.app.state.cache


CacheDep = Annotated[RedisGuard, Depends(get_cache)]
