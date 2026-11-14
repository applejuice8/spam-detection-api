import hashlib
import json
from fastapi import APIRouter
from fastapi.concurrency import run_in_threadpool
from redis.exceptions import RedisError
from app.predict.schemas import PredictRequest, PredictResponse
from app.predict.dependencies import RedisDep, SpamClassifierDep
from app.auth.dependencies import APIKeyUserDep
from app.core.metrics import MODEL_INFERENCE_SECONDS, PREDICTION_CACHE, PREDICTIONS


router = APIRouter(prefix='/predict', tags=['predict'])

CACHE_TTL_SECONDS = 3600


# Hash keeps keys short and keeps raw user text out of Redis. The model version stops old predictions being reused after retraining.
def cache_key(text: str, model_version: str) -> str:
    return f'spam:{model_version}:{hashlib.sha256(text.encode()).hexdigest()}'


@router.post('', response_model=PredictResponse)
async def predict(req: PredictRequest, model: SpamClassifierDep, user: APIKeyUserDep, r: RedisDep):
    key = cache_key(req.text, model.version)

    # The cache is optional: if Redis is down, carry on without it
    try:
        cached = await r.get(key)
    except RedisError:
        cached = None
        PREDICTION_CACHE.labels(result='error').inc()
    else:
        PREDICTION_CACHE.labels(result='hit' if cached is not None else 'miss').inc()

    if cached is not None:
        result = json.loads(cached)
        PREDICTIONS.labels(label=result['label']).inc()
        return PredictResponse(**result, model_f1=model.metadata['f1'], from_cache=True)

    # CPU bound, so run it in a thread instead of blocking the event loop
    with MODEL_INFERENCE_SECONDS.time():
        result = (await run_in_threadpool(model.predict, [req.text]))[0]
    PREDICTIONS.labels(label=result['label']).inc()

    try:
        await r.set(key, json.dumps(result), ex=CACHE_TTL_SECONDS)
    except RedisError:
        pass

    return PredictResponse(**result, model_f1=model.metadata['f1'], from_cache=False)
