from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import asyncio
from contextlib import asynccontextmanager, suppress
from app.ml_model import SpamClassifier
from app.auth.router import router as auth_router
from app.auth.maintenance import purge_loop
from app.db import async_session
from app.predict.router import router as predict_router
from app.core.config import get_settings
from app.core.metrics import MODEL_F1
from redis.asyncio import Redis
from app.core.cache import RedisGuard
from prometheus_fastapi_instrumentator import Instrumentator


# Loads redis, model once. Also starts the periodic cleanup of expired tokens.
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Short timeouts, and RedisGuard skips Redis for a while after a failure, so a down Redis costs one slow request at most
    app.state.cache = RedisGuard(Redis.from_url(
        get_settings().redis_url,
        decode_responses=True,
        socket_timeout=1,
        socket_connect_timeout=1
    ))
    app.state.spam_classifier = SpamClassifier()
    MODEL_F1.labels(model_version=app.state.spam_classifier.version).set(app.state.spam_classifier.metadata['f1'])
    purge_task = asyncio.create_task(purge_loop(async_session))
    yield
    purge_task.cancel()
    with suppress(asyncio.CancelledError):
        await purge_task
    await app.state.cache.aclose()


app = FastAPI(lifespan=lifespan)


app.add_middleware(
    CORSMiddleware,
    allow_origins=get_settings().allowed_origins,
    allow_methods=['*'],
    allow_headers=['*']
)


# Prometheus
instrumentator = Instrumentator(
    should_group_status_codes=True,
    excluded_handlers=['/metrics'],
    should_instrument_requests_inprogress=True
)
# Hidden from /docs. /metrics shows internals, so keep it off the public internet in production
instrumentator.instrument(app).expose(app, include_in_schema=False)


app.include_router(auth_router)
app.include_router(predict_router)


@app.get('/health')
async def health():
    return {'status': 'ok'}
