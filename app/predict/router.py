from fastapi import APIRouter
from app.predict.schemas import PredictRequest, PredictResponse
from app.predict.dependencies import RedisDep, SpamClassifierDep
from app.auth.dependencies import APIKeyUserDep


router = APIRouter(prefix='/predict', tags=['predict'])


# CPU bound, no async
@router.post('', response_model=PredictResponse)
async def predict(req: PredictRequest, model: SpamClassifierDep, user: APIKeyUserDep, r: RedisDep):
    cached = await r.get(f'spam:{req.text}')
    if cached is not None:
        return PredictResponse(**cached, from_cache=True)
    
    result = model.predict([req.text])[0]
    await r.set(f'spam:{req.text}', result, ex=3600)
    return PredictResponse(**result, model_f1=model.metadata['f1'], from_cache=False)
