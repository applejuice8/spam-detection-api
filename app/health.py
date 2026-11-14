from fastapi import APIRouter, HTTPException, Request, status
from sqlalchemy import text
from app.db import DBDep


router = APIRouter(tags=['health'])


# Liveness: the process is up and serving. Used by the container health check.
@router.get('/health')
async def health():
    return {'status': 'ok'}


# Readiness: the API can actually answer requests. Redis is optional, so it is not checked.
@router.get('/ready')
async def ready(req: Request, db: DBDep):
    if getattr(req.app.state, 'spam_classifier', None) is None:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, 'Model not loaded')
    try:
        await db.execute(text('SELECT 1'))
    except Exception:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, 'Database unavailable') from None
    return {'status': 'ready'}
