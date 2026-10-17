from fastapi import FastAPI
from contextlib import asynccontextmanager
from app.ml_model import SpamClassifier
from app.auth.router import router as auth_router
from app.predict.router import router as predict_router


# Loads model once
@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.spam_classifier = SpamClassifier()
    yield


app = FastAPI(lifespan=lifespan)
app.include_router(auth_router)
app.include_router(predict_router)


@app.get('/health')
async def health():
    return {'status': 'ok'}
