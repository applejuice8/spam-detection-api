import hashlib
import json
from fastapi import APIRouter
from fastapi.concurrency import run_in_threadpool
from pydantic import ValidationError
from app.core import rate_limit
from app.core.cache import CacheDep, CacheUnavailable
from app.predict.schemas import PredictRequest, PredictResponse
from app.predict.dependencies import SpamClassifierDep
from app.auth.dependencies import APIKeyUserDep
from app.core.metrics import MODEL_INFERENCE_SECONDS, PREDICTION_CACHE, PREDICTIONS


router = APIRouter(
    prefix='/predict', tags=['predict'],
    dependencies=[rate_limit.limit_by_ip('predict_ip')]     # Runs before the API key lookup
)

CACHE_TTL_SECONDS = 3600


# Hash keeps keys short and keeps raw user text out of Redis
def cache_key(text: str, model_version: str) -> str:
    return f'spam:{model_version}:{hashlib.sha256(text.encode()).hexdigest()}'


# If Redis is down, or an entry is unreadable, treat it as a miss
async def read_cache(cache: CacheDep, key: str) -> dict | None:
    try:
        cached = await cache.get(key)
    except CacheUnavailable:
        PREDICTION_CACHE.labels(result='error').inc()
        return None

    if cached is None:
        PREDICTION_CACHE.labels(result='miss').inc()
        return None

    try:
        result = json.loads(cached)
        PredictResponse(**result, from_cache=True)       # Validates shape
    except (ValueError, TypeError, ValidationError):
        PREDICTION_CACHE.labels(result='error').inc()
        return None

    PREDICTION_CACHE.labels(result='hit').inc()
    return result


@router.post('', response_model=PredictResponse)
async def predict(req: PredictRequest, model: SpamClassifierDep, user: APIKeyUserDep, cache: CacheDep):
    await rate_limit.enforce(cache, 'predict_user', str(user.id))

    key = cache_key(req.text, model.version)

    result = await read_cache(cache, key)
    if result is not None:
        PREDICTIONS.labels(label=result['label']).inc()
        return PredictResponse(**result, from_cache=True)

    # CPU bound, run it in a thread instead of blocking the event loop
    with MODEL_INFERENCE_SECONDS.time():
        result = (await run_in_threadpool(model.predict, [req.text]))[0]
    PREDICTIONS.labels(label=result['label']).inc()

    await cache.set(key, json.dumps(result), ex=CACHE_TTL_SECONDS)

    return PredictResponse(**result, from_cache=False)
