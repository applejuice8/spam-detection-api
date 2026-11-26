import asyncio
import hmac
from contextlib import asynccontextmanager, suppress
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from app.ml_model import SpamClassifier
from app.auth.router import router as auth_router
from app.auth.purge import purge_loop
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

    # Load redis
    app.state.cache = RedisGuard(Redis.from_url(
        settings.redis_url,
        decode_responses=True,      # Bytes to str
        socket_timeout=1,
        socket_connect_timeout=1
    ))

    # Load model
    app.state.spam_classifier = SpamClassifier(threshold=settings.spam_threshold)
    MODEL_F1.labels(model_version=app.state.spam_classifier.version).set(app.state.spam_classifier.metadata['f1'])

    # Prometheus gets a separate port that is not published to the internet
    app.state.metrics_server, _ = start_http_server(settings.metrics_port, addr=settings.metrics_host)

    # Background coroutine delete old rows periodically
    purge_task = asyncio.create_task(purge_loop(async_session))
    yield

    # Close background coroutine
    purge_task.cancel()
    with suppress(asyncio.CancelledError):
        await purge_task

    # Close prometheus
    app.state.metrics_server.shutdown()
    app.state.metrics_server.server_close()

    # Close redis
    await app.state.cache.aclose()


app = FastAPI(lifespan=lifespan)


@app.middleware('http')
async def protect_metrics_endpoint(request: Request, call_next):
    if request.url.path == '/metrics':
        token = get_settings().metrics_bearer_token
        if token and not hmac.compare_digest(
            request.headers.get('authorization', ''), f'Bearer {token}'
        ):
            return JSONResponse(
                {'detail': 'Not authenticated'},
                status_code=401,
                headers={'WWW-Authenticate': 'Bearer'},
            )
    return await call_next(request)


# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=get_settings().allowed_origins,
    allow_methods=['*'],
    allow_headers=['*']
)


# Keep the internal metrics listener for the Compose Prometheus service; expose the same registry on
# the API port so hosted scrapers can reach it through the single public Render HTTP port.
Instrumentator(should_group_status_codes=True, should_instrument_requests_inprogress=True).instrument(app).expose(
    app, endpoint='/metrics', include_in_schema=False
)


# Routers
app.include_router(health_router)
app.include_router(auth_router)
app.include_router(predict_router)
