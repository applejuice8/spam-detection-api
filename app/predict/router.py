from fastapi import APIRouter
from app.predict.schemas import PredictRequest, PredictResponse
from app.predict.dependencies import SpamClassifierDep
from app.auth.dependencies import APIKeyUserDep


router = APIRouter(prefix='/predict', tags=['predict'])


# CPU bound, no async
@router.post('', response_model=PredictResponse)
def predict(req: PredictRequest, model: SpamClassifierDep, user: APIKeyUserDep):
    result = model.predict([req.text])[0]
    return PredictResponse(**result, model_f1=model.metadata['f1'])
