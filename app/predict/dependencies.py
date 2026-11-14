from fastapi import Request, Depends
from app.ml_model import SpamClassifier
from typing import Annotated
from redis.asyncio import Redis


async def get_redis(req: Request) -> Redis:
    return req.app.state.redis


def get_spam_classifier(req: Request) -> SpamClassifier:
    return req.app.state.spam_classifier


RedisDep = Annotated[Redis, Depends(get_redis)]
SpamClassifierDep = Annotated[SpamClassifier, Depends(get_spam_classifier)]
