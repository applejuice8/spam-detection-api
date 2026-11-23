from fastapi import Depends, HTTPException, Request, status
from app.core.cache import CacheDep, CacheUnavailable
from app.core.metrics import RATE_LIMITED


# Looked up on every request, so a limit can be changed at runtime (tests do).
LIMITS = {
    'login': (10, 60),              # Per client IP. Slows password guessing.
    'signup': (5, 3600),            # Per client IP
    'refresh': (30, 60),            # Per client IP
    'predict_ip': (300, 60),        # Per client IP, before the API key lookup, so key guessing can't hammer the database
    'predict_user': (60, 60),       # Per API key owner
}


def client_ip(req: Request) -> str:
    # Behind a reverse proxy this is the proxy's address
    return req.client.host if req.client else 'unknown'


# Counted in Redis. If Redis is down the limit is skipped rather than locking everyone out.
async def enforce(cache, scope: str, identity: str) -> None:
    max_requests, window = LIMITS[scope]
    try:
        used = await cache.count(f'rl:{scope}:{identity}', window)
    except CacheUnavailable:
        return

    if used > max_requests:
        RATE_LIMITED.labels(scope=scope).inc()
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            'Too many requests. Try again later.',
            headers={'Retry-After': str(window)}
        )


# Dependency factory
def limit_by_ip(scope: str):
    async def dependency(req: Request, cache: CacheDep) -> None:    # Run on every request
        await enforce(cache, scope, client_ip(req))
    return Depends(dependency)
