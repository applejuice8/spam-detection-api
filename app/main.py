import asyncio
from contextlib import asynccontextmanager, suppress
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.ml_model import SpamClassifier
from app.auth.router import router as auth_router
from app.auth.maintenance import purge_loop
from app.db import async_session
from app.health import router as health_router
from app.predict.router import router as predict_router
from app.core.cache import RedisGuard
from app.core.config import get_settings
from app.core.metrics import MODEL_F1
from redis.asyncio import Redis
from prometheus_client import start_http_server
from prometheus_fastapi_instrumentator import Instrumentator


# Loads redis, model once. Starts the metrics server and the periodic cleanup of expired tokens.
@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()

    # Short timeouts, and RedisGuard skips Redis for a while after a failure, so a down Redis costs one slow request at most
    app.state.cache = RedisGuard(Redis.from_url(
        settings.redis_url,
        decode_responses=True,
        socket_timeout=1,
        socket_connect_timeout=1
    ))
    app.state.spam_classifier = SpamClassifier(threshold=settings.spam_threshold)
    MODEL_F1.labels(model_version=app.state.spam_classifier.version).set(app.state.spam_classifier.metadata['f1'])

    # /metrics shows internals, so it gets a separate port that is not published to the internet
    app.state.metrics_server, _ = start_http_server(settings.metrics_port, addr=settings.metrics_host)

    purge_task = asyncio.create_task(purge_loop(async_session))
    yield
    purge_task.cancel()
    with suppress(asyncio.CancelledError):
        await purge_task
    app.state.metrics_server.shutdown()
    app.state.metrics_server.server_close()
    await app.state.cache.aclose()


app = FastAPI(lifespan=lifespan)


app.add_middleware(
    CORSMiddleware,
    allow_origins=get_settings().allowed_origins,
    allow_methods=['*'],
    allow_headers=['*']
)


# Prometheus: collects HTTP metrics. They are served by the metrics server started in lifespan, not by this app.
Instrumentator(should_group_status_codes=True, should_instrument_requests_inprogress=True).instrument(app)


app.include_router(health_router)
app.include_router(auth_router)
app.include_router(predict_router)
