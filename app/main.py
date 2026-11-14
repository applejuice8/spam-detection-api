from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from app.ml_model import SpamClassifier
from app.auth.router import router as auth_router
from app.predict.router import router as predict_router
from app.core.config import get_settings
from redis.asyncio import Redis
from prometheus_fastapi_instrumentator import Instrumentator


# Loads redis, model once
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Short timeouts so a down Redis slows a request by at most about a second, then predict falls back to the model
    app.state.redis = Redis.from_url(
        get_settings().redis_url,
        decode_responses=True,
        socket_timeout=1,
        socket_connect_timeout=1
    )
    app.state.spam_classifier = SpamClassifier()
    yield
    await app.state.redis.aclose()


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
instrumentator.instrument(app).expose(app)


app.include_router(auth_router)
app.include_router(predict_router)


@app.get('/health')
async def health():
    return {'status': 'ok'}
